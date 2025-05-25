import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'votre_clef_secrete_très_complexe_et_unique'
    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'database.db')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Clé API OpenAI (Pardonnez les gas a ne pas partager s'il vous plait 😏😥)
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY') or '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'
