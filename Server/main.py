from flask import Flask, jsonify, Response, request, session
from flask_cors import CORS
import requests
import logging
from models import db, User, Stock, Portfolio, PortfolioStock
from sqlalchemy.pool import NullPool
import oracledb
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Sequence
import datetime

app = Flask(__name__)
CORS(app, supports_credentials=True)
ALPHA_VANTAGE_API_KEY = 'ZBD3QIPITMQNSPPF'
app.secret_key = 'mysecretkey'

un = 'myownsh'
pw = 'AaZZ0r_cle#1'
dsn = '(description= (retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1521)(host=adb.eu-madrid-1.oraclecloud.com))(connect_data=(service_name=g94a0d92b10bb94_p1plm1xfn2614jm8_high.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))'

pool = oracledb.create_pool(user=un, password=pw, dsn=dsn)

app.config['SQLALCHEMY_DATABASE_URI'] = 'oracle+oracledb://'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'creator': pool.acquire,
    'poolclass': NullPool
}
app.config['SQLALCHEMY_ECHO'] = True
app.config['SECRET_KEY'] = 'mysecretkey'
db.init_app(app)



@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('NAME')
        password = data.get('PASSWORD_HASH')

        user = User.query.filter_by(NAME=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.USER_ID  # Store user ID in session
            return jsonify({'message': 'Login successful', 'USER_ID': user.USER_ID}), 200
        else:
            return jsonify({'message': 'Invalid username or password'}), 401
    except Exception as e:
        app.logger.error(f"An error occurred: {e}")
        return jsonify({'message': 'An error occurred'}), 500


@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        email = data.get('EMAIL')
        username = data.get('NAME')
        password = data.get('PASSWORD_HASH')
        existing_user = User.query.filter_by(NAME=username).first()
        if existing_user:
            return jsonify({'message': 'User already exists'}), 409
        new_user = User(NAME=username)
        seq_val = db.session.execute(Sequence('user_id_seq'))
        new_user.USER_ID = seq_val
        new_user.EMAIL = email
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return jsonify({'message': 'User created successfully'}), 201
    except Exception as e:
        app.logger.error(f"An error occurred: {e}")
        return jsonify({'message': 'An error occurred'}), 500


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    if 'user_id' in session:
        session.pop('user_id')
        return jsonify({'message': 'User logged out'}), 200
    else:
        return jsonify({'message': 'User is not logged in'}), 401


@app.route('/api/portfolio/add', methods=['POST'])
def add_stock_to_portfolio():
    data = request.json
    symbol = data.get('SYMBOL')
    added_quantity = data.get('QUANTITY')
    user_id = session.get('USER_ID')

    fetch_stock_details = lambda symbol: requests.get(
        f'https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={symbol}&apikey={ALPHA_VANTAGE_API_KEY}'
    ).json().get('bestMatches')[0].get('2. name')

    if not user_id:
        return jsonify({'message': 'User is not logged in.'}), 401

    stock = Stock.query.filter_by(SYMBOL=symbol).first()
    if not stock:
        stock_name = fetch_stock_details(symbol)
        if not stock_name:
            return jsonify({'message': 'Stock details not found'}), 404

        stock = Stock(SYMBOL=symbol, NAME=stock_name)
        db.session.add(stock)
        db.session.commit()

    portfolio = Portfolio.query.filter_by(USER_ID=user_id).first()
    if not portfolio:
        portfolio = Portfolio(USER_ID=user_id)
        db.session.add(portfolio)
        db.session.commit()

    portfolio_stock = PortfolioStock.query.filter_by(
        PORTFOLIO_ID=portfolio.PORTFOLIO_ID,
        STOCK_ID=stock.STOCK_ID
    ).first()

    if portfolio_stock:
        portfolio_stock.QUANTITY += added_quantity
    else:
        portfolio_stock = PortfolioStock(
            PORTFOLIO_ID=portfolio.PORTFOLIO_ID,
            STOCK_ID=stock.STOCK_ID,
            QUANTITY=added_quantity,
            ACQUISITION_PRICE=data.get('ACQUISITION_PRICE'),
            ACQUISITION_DATE= datetime.datetime.now()
        )
        db.session.add(portfolio_stock)

    db.session.commit()

    return jsonify({
        'message': 'Stock quantity updated in portfolio',
        'updated_quantity': portfolio_stock.QUANTITY
    }), 200


@app.route('/api/portfolio/', methods=['GET'])
def view_portfolio():
    user_id = session.get('USER_ID')
    if not user_id:
        return jsonify({"error": "User not logged in"}), 401

    portfolio = Portfolio.query.filter_by(USER_ID=user_id).first()

    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404

    portfolio_stocks = PortfolioStock.query.filter_by(PORTFOLIO_ID=portfolio.PORTFOLIO_ID).all()
    stocks_details = []
    for ps in portfolio_stocks:
        stock = Stock.query.filter_by(STOCK_ID=ps.STOCK_ID).first()
        if stock:
            stock_detail = {
                'STOCK_ID': ps.STOCK_ID,  # Changed 'id' to 'stock_id' to avoid conflict with 'id' in the response
                "SYMBOL": stock.SYMBOL,
                "NAME": stock.NAME,
                "QUANTITY": ps.QUANTITY,
                "ACQUISITION_PRICE": ps.ACQUISITION_PRICE,
                "ACQUISITION_DATE": ps.ACQUISITION_DATE
            }
            stocks_details.append(stock_detail)
        else:
            app.logger.error(f"Stock with ID {ps.STOCK_ID} not found in the STOCK table")

    return jsonify(stocks_details), 200


@app.route('/api/portfolio/create', methods=['POST'])
def create_portfolio():
    user_id = session.get('USER_ID')
    if not user_id:
        return jsonify({"error": "User not logged in"}), 401

    portfolio = Portfolio.query.filter_by(USER_ID=user_id).first()
    if portfolio:
        return jsonify({"error": "Portfolio already exists"}), 409

    new_portfolio_id = db.session.execute(Sequence('portfolio_id_seq')).scalar()
    new_portfolio = Portfolio(USER_ID=user_id)
    new_portfolio.PORTFOLIO_ID = new_portfolio_id
    db.session.add(new_portfolio)
    db.session.commit()


    return jsonify({"message": "Portfolio created successfully"}), 201


@app.route('/api/all-stocks/')
def all_stocks():
    url = f'https://www.alphavantage.co/query?function=LISTING_STATUS&apikey={ALPHA_VANTAGE_API_KEY}'

    try:
        response = requests.get(url)
        if response.status_code == 200:
            return Response(response.content, content_type='text/csv')
        else:
            logging.error(f"Error fetching data from Alpha Vantage: HTTP {response.status_code}")
            return jsonify({"error": "Failed to fetch data from Alpha Vantage"}), response.status_code
    except requests.RequestException as e:
        print(f"Request to Alpha Vantage failed: {e}")
        return jsonify({"error": "Failed to connect to Alpha Vantage"}), 500


@app.route('/api/stock/<symbol>')
def stock_data(symbol):
    url = f'https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}'
    response = requests.get(url)
    return jsonify(response.json())


@app.route('/api/quote/<symbol>')
def stock_quote(symbol):
    url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}'
    response = requests.get(url)
    return jsonify(response.json())


if __name__ == '__main__':
    app.run(debug=False)
