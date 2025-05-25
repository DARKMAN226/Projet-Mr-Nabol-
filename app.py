import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, session, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, DateField, StringField, SubmitField
from wtforms.validators import DataRequired, NumberRange
from openai import OpenAI
import io

# Pour la génération PDF
from weasyprint import HTML

# Initialisation app et config
app = Flask(__name__)
app.config.from_object('config.Config')

if not app.config.get('SECRET_KEY'):
    app.config['SECRET_KEY'] = os.urandom(24)

db = SQLAlchemy(app)

# OpenAI client
openai_api_key = app.config.get('OPENAI_API_KEY', '')
client = OpenAI(api_key=openai_api_key)

# Modèle base de données
class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    type = db.Column(db.String(10), nullable=False)  # 'depense' ou 'revenu'

# Formulaires
class TransactionForm(FlaskForm):
    amount = DecimalField('Montant (€)', validators=[DataRequired(), NumberRange(min=0.01)])
    category = SelectField('Catégorie', choices=[], validators=[DataRequired()])
    date = DateField('Date', default=datetime.today, validators=[DataRequired()])
    submit = SubmitField('Enregistrer')

class ChatForm(FlaskForm):
    message = StringField('Votre message', validators=[DataRequired()])
    submit = SubmitField('Envoyer')

# Catégories
DEPENSE_CATEGORIES = [('nourriture', 'Nourriture'), ('loyer', 'Loyer'), ('loisirs', 'Loisirs'), ('autres', 'Autres')]
REVENU_CATEGORIES = [('bourse', 'Bourse'), ('job', 'Job étudiant'), ('autres', 'Autres')]

# Routes

@app.route('/')
def index():
    total_revenus = db.session.query(db.func.sum(Transaction.amount)).filter_by(type='revenu').scalar() or 0
    total_depenses = db.session.query(db.func.sum(Transaction.amount)).filter_by(type='depense').scalar() or 0
    solde = total_revenus - total_depenses

    cat_depense = db.session.query(Transaction.category, db.func.sum(Transaction.amount).label('total'))\
        .filter_by(type='depense').group_by(Transaction.category).order_by(db.desc('total')).first()
    categorie_principale = cat_depense.category if cat_depense else "Aucune"

    return render_template('index.html', solde=solde, total_revenus=total_revenus,
                           total_depenses=total_depenses, categorie_principale=categorie_principale)

@app.route('/depenses')
def depenses():
    depenses = Transaction.query.filter_by(type='depense').order_by(Transaction.date.desc()).all()
    return render_template('depenses.html', depenses=depenses)

@app.route('/revenus')
def revenus():
    revenus = Transaction.query.filter_by(type='revenu').order_by(Transaction.date.desc()).all()
    return render_template('revenus.html', revenus=revenus)

@app.route('/ajout/depense', methods=['GET', 'POST'])
def ajout_depense():
    form = TransactionForm()
    form.category.choices = DEPENSE_CATEGORIES
    if form.validate_on_submit():
        depense = Transaction(
            amount=float(form.amount.data),
            category=form.category.data,
            date=form.date.data,
            type='depense'
        )
        db.session.add(depense)
        db.session.commit()
        flash('Dépense ajoutée avec succès.', 'success')
        return redirect(url_for('depenses'))
    return render_template('ajout_depense.html', form=form)

@app.route('/ajout/revenu', methods=['GET', 'POST'])
def ajout_revenu():
    form = TransactionForm()
    form.category.choices = REVENU_CATEGORIES
    if form.validate_on_submit():
        revenu = Transaction(
            amount=float(form.amount.data),
            category=form.category.data,
            date=form.date.data,
            type='revenu'
        )
        db.session.add(revenu)
        db.session.commit()
        flash('Revenu ajouté avec succès.', 'success')
        return redirect(url_for('revenus'))
    return render_template('ajout_revenu.html', form=form)

@app.route('/modifier/<string:type>/<int:id>', methods=['GET', 'POST'])
def modifier_transaction(type, id):
    transaction = Transaction.query.get_or_404(id)
    if transaction.type != type:
        flash("Type de transaction incorrect.", "danger")
        return redirect(url_for('index'))
    form = TransactionForm(obj=transaction)
    form.category.choices = DEPENSE_CATEGORIES if type == 'depense' else REVENU_CATEGORIES
    if form.validate_on_submit():
        transaction.amount = float(form.amount.data)
        transaction.category = form.category.data
        transaction.date = form.date.data
        db.session.commit()
        flash(f'{type.capitalize()} modifié(e) avec succès.', 'success')
        return redirect(url_for(type + 's'))
    return render_template('ajout_depense.html' if type == 'depense' else 'ajout_revenu.html', form=form, modifier=True)

@app.route('/supprimer/<string:type>/<int:id>', methods=['POST'])
def supprimer_transaction(type, id):
    transaction = Transaction.query.get_or_404(id)
    if transaction.type != type:
        flash("Type de transaction incorrect.", "danger")
        return redirect(url_for('index'))
    db.session.delete(transaction)
    db.session.commit()
    flash(f'{type.capitalize()} supprimé(e) avec succès.', 'success')
    return redirect(url_for(type + 's'))

@app.route('/dashboard')
def dashboard():
    from sqlalchemy import extract
    import calendar
    today = datetime.today()

    depenses_categorie = db.session.query(Transaction.category, db.func.sum(Transaction.amount))\
        .filter_by(type='depense').group_by(Transaction.category).all()
    depenses_par_categorie = {cat: total for cat, total in depenses_categorie}

    evolution_mensuelle = {}
    for i in range(5, -1, -1):
        month = (today.month - i - 1) % 12 + 1
        year = today.year if today.month - i > 0 else today.year - 1
        total = db.session.query(db.func.sum(Transaction.amount))\
            .filter_by(type='depense')\
            .filter(db.extract('month', Transaction.date) == month)\
            .filter(db.extract('year', Transaction.date) == year).scalar() or 0
        evolution_mensuelle[f"{calendar.month_abbr[month]} {year}"] = total

    return render_template('dashboard.html',
                           depenses_par_categorie=depenses_par_categorie,
                           evolution_mensuelle=evolution_mensuelle)

@app.route('/chat_ia', methods=['GET', 'POST'])
def chat_ia():
    form = ChatForm()
    if 'chat_history' not in session:
        session['chat_history'] = []

    error_openai = None

    if form.validate_on_submit():
        user_message = form.message.data
        session['chat_history'].append({'user': 'Utilisateur', 'text': user_message})

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Tu es un assistant budgétaire pour étudiants."},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=150,
                temperature=0.7
            )
            ai_message = response.choices[0].message.content
        except Exception as e:
            if "insufficient_quota" in str(e):
                ai_message = "Votre quota OpenAI est dépassé. Merci de vérifier votre compte ou d'attendre le renouvellement."
            else:
                ai_message = "Désolé, une erreur est survenue lors de la communication avec l'IA."
            error_openai = e

        if error_openai:
            app.logger.error(f"Erreur OpenAI : {error_openai}")

        session['chat_history'].append({'user': 'IA', 'text': ai_message})
        form.message.data = ''
        session.modified = True

    return render_template('chat_ia.html', form=form, chat_history=session.get('chat_history', []))

@app.route('/rapport_pdf')
def rapport_pdf():
    from sqlalchemy import extract
    import calendar

    date_rapport = datetime.today()
    total_revenus = db.session.query(db.func.sum(Transaction.amount)).filter_by(type='revenu').scalar() or 0
    total_depenses = db.session.query(db.func.sum(Transaction.amount)).filter_by(type='depense').scalar() or 0
    solde = total_revenus - total_depenses

    depenses_categorie = db.session.query(Transaction.category, db.func.sum(Transaction.amount))\
        .filter_by(type='depense').group_by(Transaction.category).all()
    depenses_par_categorie = {cat: total for cat, total in depenses_categorie}

    evolution_mensuelle = {}
    today = datetime.today()
    for i in range(5, -1, -1):
        month = (today.month - i - 1) % 12 + 1
        year = today.year if today.month - i > 0 else today.year - 1
        total = db.session.query(db.func.sum(Transaction.amount))\
            .filter_by(type='depense')\
            .filter(extract('month', Transaction.date) == month)\
            .filter(extract('year', Transaction.date) == year).scalar() or 0
        evolution_mensuelle[f"{calendar.month_abbr[month]} {year}"] = total

    html = render_template(
        'rapport_pdf.html',
        date_rapport=date_rapport,
        solde=solde,
        total_revenus=total_revenus,
        total_depenses=total_depenses,
        depenses_par_categorie=depenses_par_categorie,
        evolution_mensuelle=evolution_mensuelle
    )

    # Génération du PDF avec WeasyPrint
    pdf = HTML(string=html).write_pdf()
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': 'inline; filename=rapport_budget.pdf'})

# Commande CLI pour initialiser la base
@app.cli.command('initdb')
def initdb_command():
    db.create_all()
    print('✅ Base de données initialisée.')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)

