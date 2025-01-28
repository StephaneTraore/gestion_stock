from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from flask_cors import CORS
import mysql.connector
import logging
import bcrypt 
import functools

app = Flask(__name__)
# clé secret
app.secret_key = 'votre_clé_secrète_très_longue_et_aléatoire'  
CORS(app, resources={r"/*": {"origins": "http://127.0.0.1:5000"}}, supports_credentials=True)


# Configuration du logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Décorateur pour protéger les routes
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Non autorisé', 'redirect': '/'}), 401
        return f(*args, **kwargs)
    return decorated_function


# Fonction pour établir la connexion à la base de données
def get_db_connection():
    try:
        conn = mysql.connector.connect(
             host= "localhost",
             user= "root",
             password= "",  #votre mot de pas Mysql ici
             database= "gestion_stock",
        )
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Erreur de connexion à la base de données: {err}")
        raise

# Middleware pour ajouter les en-têtes CORS à toutes les réponses
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response



# créer un username et un mot de pass hasché par default: username: admin, mot de passe: admin123
def create_admin_user():
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt())
    cursor.execute(
        "INSERT IGNORE INTO users (username, password) VALUES (%s, %s)",
        ("admin", password_hash),
    )
    conn.commit()
    cursor.close()
    conn.close()
    
    
# la Route de login 
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Nom d\'utilisateur et mot de passe requis'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return jsonify({'message': 'Connexion réussie', 'redirect': '/index'}), 200
        else:
            return jsonify({'error': 'Nom d\'utilisateur ou mot de passe invalide'}), 401

    except Exception as e:
        return jsonify({'error': f"Erreur serveur : {str(e)}"}), 500


# Route de logout
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Déconnexion réussie', 'redirect': '/'}), 200



# Route vers l'interface login
@app.route('/')
def serve_login():
    return send_from_directory('.', 'login.html')

# Route vers l'interface ajout/modification de produit
@app.route('/index')
@login_required
def serve_index():
    return send_from_directory('.', 'index.html')

# Route vers l'interface de la page vente
@app.route('/ventes')
@login_required
def serve_vente():
    return send_from_directory('.', 'ventes.html')


#Route Api effectuer une vente.
@app.route('/api/ventes', methods=['POST'])
@login_required
def effectuer_vente():
    try:
        # Récupérer les données de la requête
        data = request.json
        produit_id = data.get('produit_id')
        quantite_vendue = data.get('quantite')
        prix_unitaire = data.get('prix_unitaire')

        if not (produit_id and quantite_vendue and prix_unitaire):
            return jsonify({'error': 'Les champs produit_id, quantite, et prix_unitaire sont requis'}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Vérifier si le produit existe et récupérer son stock
        cursor.execute("SELECT * FROM produits WHERE id = %s", (produit_id,))
        produit = cursor.fetchone()

        if not produit:
            return jsonify({'error': 'Produit non trouvé'}), 404

        # Vérifier si le stock est suffisant
        if produit['quantite'] < quantite_vendue:
            return jsonify({'error': 'Quantité insuffisante en stock'}), 400

        # Calculer le total de la vente
        total = quantite_vendue * prix_unitaire

        # Insérer la vente dans la table ventes
        query_vente = """
        INSERT INTO ventes (produit_id, quantite, prix_unitaire, total)
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query_vente, (produit_id, quantite_vendue, prix_unitaire, total))

        # Mettre à jour le stock du produit
        query_update = "UPDATE produits SET quantite = quantite - %s WHERE id = %s"
        cursor.execute(query_update, (quantite_vendue, produit_id))

        # Confirmer les modifications
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'message': 'Vente effectuée avec succès', 'vente_id': cursor.lastrowid}), 201

    except mysql.connector.Error as err:
        logger.error(f"Erreur MySQL: {err}")
        return jsonify({'error': f"Erreur de base de données: {str(err)}"}), 500
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")
        return jsonify({'error': f"Erreur inattendue: {str(e)}"}), 500




# Route api historique des ventes
@app.route('/api/ventes', methods=['GET'])
@login_required
def historique_ventes():
    try:
        # Établir une connexion à la base de données
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Requête SQL pour récupérer l'historique des ventes
        query = """
        SELECT v.id AS vente_id, p.nom AS produit_nom, v.quantite, v.prix_unitaire, v.total, v.date_vente
        FROM ventes v
        JOIN produits p ON v.produit_id = p.id
        ORDER BY v.date_vente DESC
        """
        cursor.execute(query)
        ventes = cursor.fetchall()

        # Fermer le curseur et la connexion
        cursor.close()
        conn.close()

        # Retourner l'historique des ventes sous forme de JSON
        return jsonify(ventes)

    except mysql.connector.Error as err:
        logger.error(f"Erreur MySQL: {err}")
        return jsonify({'error': f"Erreur de base de données: {str(err)}"}), 500
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")
        return jsonify({'error': f"Erreur inattendue: {str(e)}"}), 500





#Route Api pour recuperer tout les produits
@app.route('/api/produits', methods=['GET'])
@login_required
def get_produits():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM produits")
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(produits)


#Route Api pour Ajouter un produit
@app.route('/api/produits', methods=['POST'])
@login_required
def add_produit():
    try:
        data = request.json
        logger.debug(f"Données reçues: {data}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """INSERT INTO produits (nom, description, quantite, prix) 
                   VALUES (%s, %s, %s, %s)"""
        values = (data['nom'], data['description'], data['quantite'], data['prix'])
        
        logger.debug(f"Exécution de la requête: {query} avec les valeurs: {values}")
        
        cursor.execute(query, values)
        conn.commit()
        
        new_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        logger.debug(f"Produit ajouté avec succès, ID: {new_id}")
        return jsonify({'id': new_id, 'message': 'Produit ajouté avec succès'}), 201
        
    except mysql.connector.Error as err:
        logger.error(f"Erreur MySQL: {err}")
        return jsonify({'error': f"Erreur de base de données: {str(err)}"}), 500
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")
        return jsonify({'error': f"Erreur inattendue: {str(e)}"}), 500



# Route Api pour récuperer un produit
@app.route('/api/produits/<int:id>', methods=['GET'])
@login_required
def get_produit(id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM produits WHERE id = %s", (id,))
        produit = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if produit is None:
            return jsonify({'error': 'Produit non trouvé'}), 404
            
        return jsonify(produit)
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du produit: {e}")
        return jsonify({'error': str(e)}), 500



# Route Api pour modifier un produit
@app.route('/api/produits/<int:id>', methods=['PUT'])
@login_required
def update_produit(id):
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """UPDATE produits 
                   SET nom = %s, description = %s, quantite = %s, prix = %s 
                   WHERE id = %s"""
        values = (data['nom'], data['description'], data['quantite'], data['prix'], id)
        
        cursor.execute(query, values)
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Product not found'}), 404
            
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Produit mis à jour avec succès'})
        
    except KeyError as e:
        return jsonify({'error': f'Missing required field: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/produits/<int:id>', methods=['DELETE'])
@login_required
def delete_produit(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM produits WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'message': 'Produit supprimé avec succès'})


if __name__ == '__main__':
    create_admin_user() # function pour créer in user par default.
    app.run(debug=True)

