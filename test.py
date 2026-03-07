
from flask import Flask
from flask import render_template, send_from_directory, jsonify
import json


app = Flask(__name__, template_folder='.', static_folder='css')

@app.route('/')
def hello_world():
    with open('products.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    products = data.get('products', [])

    return render_template("catalog.html", products=products)

@app.route('/css/catalog.css')
def custom_static():
    return send_from_directory('css', 'catalog.css')

@app.route('/data')
def catalog():
    with open('products.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)


if __name__ == '__main__':
  app.run(debug=True)