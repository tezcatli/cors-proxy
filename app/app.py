from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Guten le monde!!!"

if __name__ == "__main__":
    app.run(host="0.0.0.0")