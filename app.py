from flask import Flask, jsonify
from flask_cors import CORS # Used to allow requests from your website's domain
import random

app = Flask(__name__)
# Enable CORS for all origins. In a production environment, you should restrict this
# to only your website's domain (e.g., CORS(app, resources={r"/api/*": {"origins": "https://yourdomain.com"}}))
CORS(app) 

# --- Data for Name Generation ---
# You can expand these lists with more names!
first_names = [
    "Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona", "George", "Hannah",
    "Ivan", "Julia", "Kevin", "Laura", "Michael", "Nora", "Oliver", "Penelope",
    "Quinn", "Rachel", "Samuel", "Tina", "Ulysses", "Victoria", "William",
    "Xavier", "Yara", "Zackary", "Sophia", "Liam", "Olivia", "Noah", "Emma",
    "Ava", "Isabella", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn", "Abigail",
    "Benjamin", "Chloe", "David", "Eleanor", "Frank", "Grace", "Henry", "Ivy",
    "Jack", "Katherine", "Leo", "Madison", "Nathan", "Piper", "Owen", "Ruby",
    "Sebastian", "Taylor", "Uma", "Vincent", "Willow", "Xenia", "Yusuf", "Zoe"
]

last_names = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Baker", "Nelson", "Carter", "Mitchell", "Roberts", "Phillips",
    "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart", "Morris", "Rogers"
]

@app.route('/generate-names/<int:count>', methods=['GET'])
def generate_multiple_names_api(count):
    """
    API endpoint to generate multiple random names.
    Accessed via GET request to /generate-names/<number_of_names>
    Example: /generate-names/5 will return 5 names.
    """
    if count <= 0:
        return jsonify({"error": "Count must be a positive integer"}), 400
    
    # Limit the number of names to prevent abuse or excessive resource usage
    if count > 100:
        return jsonify({"error": "Maximum 100 names can be generated at once"}), 400

    generated_names = []
    for _ in range(count):
        first = random.choice(first_names)
        last = random.choice(last_names)
        generated_names.append(f"{first} {last}")
    
    # Return the list of names as a JSON object
    return jsonify({"names": generated_names})

if __name__ == '__main__':
    # This block runs when you execute the script directly.
    # For local development, you can run this: python app.py
    # It will be accessible at http://127.0.0.1:5000/
    # For deployment, a production-ready WSGI server like Gunicorn is typically used.
    app.run(debug=True, port=5000)
