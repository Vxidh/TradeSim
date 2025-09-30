# server.py
# v6: Final, definitive version. All complex async dependencies (gevent, eventlet)
# have been removed to guarantee stability and prevent compatibility errors.

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import time
import random
import os

# --- App Initialization ---
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)
# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', "postgresql://neondb_owner:npg_X0IewA1PDuor@ep-square-rice-a1s1ujv6-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
# Use threading mode for SocketIO to avoid eventlet/gevent issues
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# --- Database Models ---
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(32), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    side = db.Column(db.String(8), nullable=False)
    timestamp = db.Column(db.BigInteger, nullable=False)

class OrderBookEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(32), nullable=False)
    price = db.Column(db.Float, nullable=False)
    size = db.Column(db.Integer, nullable=False)
    side = db.Column(db.String(8), nullable=False)  # 'Bid' or 'Ask'

# --- Market Data Generation (still in memory for now) ---
def generate_market_data():
    # This function is only used for chart display, not for order book or trades
    data, price, current_time = [], 2800.0, int(time.time())
    for i in range(100):
        timestamp = current_time - (100 - i) * 60
        o, h, l, c = price + random.uniform(-5, 5), 0, 0, 0
        h, l = o + random.uniform(0, 5), o - random.uniform(0, 5)
        c = random.uniform(l, h)
        data.append({"time": timestamp, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
        price = c
    return data
market_data = generate_market_data()


# --- Route to serve the frontend ---
@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend', 'tradesim.html')


# --- REST API Endpoints (unchanged) ---
@app.route('/api/market_data')
def get_market_data():
    symbol = request.args.get('symbol', 'RELIANCE')
    # Example: generate different market data for each symbol
    base_prices = {
        'AAPL': 170.0,
        'MSFT': 330.0,
        'GOOG': 2800.0,
        'AMZN': 3400.0,
        'META': 320.0,
        'TSLA': 700.0,
        'RELIANCE': 2850.0
    }
    price = base_prices.get(symbol, 100.0)
    data, current_time = [], int(time.time())
    for i in range(100):
        timestamp = current_time - (100 - i) * 60
        o, h, l, c = price + random.uniform(-5, 5), 0, 0, 0
        h, l = o + random.uniform(0, 5), o - random.uniform(0, 5)
        c = random.uniform(l, h)
        data.append({"time": timestamp, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
        price = c
    return jsonify(data)

@app.route('/api/trades')
def get_trades():
    trades = Trade.query.order_by(Trade.timestamp.desc()).all()
    result = [
        {
            'trade_id': t.id,
            'symbol': t.symbol,
            'price': t.price,
            'quantity': t.quantity,
            'side': t.side,
            'timestamp': t.timestamp
        } for t in trades
    ]
    return jsonify(result)

    symbol = request.args.get('symbol', 'RELIANCE')
    trades = Trade.query.filter_by(symbol=symbol).order_by(Trade.timestamp.desc()).all()
    result = [
        {
            'trade_id': t.id,
            'symbol': t.symbol,
            'price': t.price,
            'quantity': t.quantity,
            'side': t.side,
            'timestamp': t.timestamp
        } for t in trades
    ]
    return jsonify(result)
@app.route('/api/orderbook')
def get_orderbook():
    bids = OrderBookEntry.query.filter_by(side='Bid').order_by(OrderBookEntry.price.desc()).all()
    asks = OrderBookEntry.query.filter_by(side='Ask').order_by(OrderBookEntry.price.asc()).all()
    bids_list = [(b.price, b.size) for b in bids]
    asks_list = [(a.price, a.size) for a in asks]
    return jsonify({'bids': bids_list, 'asks': asks_list})

    symbol = request.args.get('symbol', 'RELIANCE')
    bids = OrderBookEntry.query.filter_by(symbol=symbol, side='Bid').order_by(OrderBookEntry.price.desc()).all()
    asks = OrderBookEntry.query.filter_by(symbol=symbol, side='Ask').order_by(OrderBookEntry.price.asc()).all()
    bids_list = [(b.price, b.size) for b in bids]
    asks_list = [(a.price, a.size) for a in asks]
    return jsonify({'bids': bids_list, 'asks': asks_list})
@app.route('/api/order', methods=['POST'])
def place_order():
    order = request.json
    print(f"--- Received New Order: {order.get('side')} {order.get('quantity')} @ {order.get('price', 'Market')} ---")
    trade_price = market_data[-1]['close'] + random.uniform(-0.5, 0.5)
    new_trade = Trade(
        symbol=order.get('symbol'),
        price=round(trade_price, 2),
        quantity=int(order.get('quantity')),
        side=order.get('side'),
        timestamp=int(time.time() * 1000)
    )
    db.session.add(new_trade)
    db.session.commit()
    trade_dict = {
        'trade_id': new_trade.id,
        'symbol': new_trade.symbol,
        'price': new_trade.price,
        'quantity': new_trade.quantity,
        'side': new_trade.side,
        'timestamp': new_trade.timestamp
    }
    socketio.emit('new_trade', trade_dict)

    # Update order book
    if order.get('side') == 'Buy':
        best_ask = OrderBookEntry.query.filter_by(side='Ask').order_by(OrderBookEntry.price.asc()).first()
        if best_ask:
            best_ask.size = max(0, best_ask.size - int(order.get('quantity')))
            if best_ask.size == 0:
                db.session.delete(best_ask)
            db.session.commit()
    elif order.get('side') == 'Sell':
        best_bid = OrderBookEntry.query.filter_by(side='Bid').order_by(OrderBookEntry.price.desc()).first()
        if best_bid:
            best_bid.size = max(0, best_bid.size - int(order.get('quantity')))
            if best_bid.size == 0:
                db.session.delete(best_bid)
            db.session.commit()

    # Emit updated order book
    bids = OrderBookEntry.query.filter_by(side='Bid').order_by(OrderBookEntry.price.desc()).all()
    asks = OrderBookEntry.query.filter_by(side='Ask').order_by(OrderBookEntry.price.asc()).all()
    bids_list = [(b.price, b.size) for b in bids]
    asks_list = [(a.price, a.size) for a in asks]
    socketio.emit('order_book_update', {'bids': bids_list, 'asks': asks_list})
    return jsonify({'status': 'success', 'message': 'Order received'}), 200


# --- SocketIO Event Handlers (unchanged) ---
@socketio.on('connect')
def handle_connect(): print('Client connected')

@socketio.on('disconnect')
def handle_disconnect(): print('Client disconnected')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print('Database tables created or already exist.')
        # Pre-populate order book for major tech stocks if empty
        if OrderBookEntry.query.count() == 0:
            tech_stocks = {
                'AAPL': {'bids': [(170.10, 200), (169.80, 150), (169.50, 100)], 'asks': [(170.50, 180), (170.80, 120), (171.00, 80)]},
                'MSFT': {'bids': [(330.20, 180), (329.90, 140), (329.50, 90)], 'asks': [(330.60, 160), (330.90, 110), (331.20, 70)]},
                'GOOG': {'bids': [(2800.50, 120), (2800.00, 100), (2799.50, 80)], 'asks': [(2801.00, 110), (2801.50, 90), (2802.00, 70)]},
                'AMZN': {'bids': [(3400.10, 150), (3399.80, 120), (3399.50, 90)], 'asks': [(3400.50, 130), (3400.80, 100), (3401.00, 80)]},
                'META': {'bids': [(320.20, 170), (319.90, 130), (319.50, 100)], 'asks': [(320.60, 150), (320.90, 110), (321.20, 80)]},
                'TSLA': {'bids': [(700.10, 160), (699.80, 120), (699.50, 90)], 'asks': [(700.50, 140), (700.80, 100), (701.00, 70)]},
                'RELIANCE': {'bids': [(2850.50, 100), (2850.25, 150), (2850.00, 200)], 'asks': [(2851.00, 120), (2851.25, 180), (2851.50, 250)]}
            }
            for symbol, book in tech_stocks.items():
                for price, size in book['bids']:
                    db.session.add(OrderBookEntry(symbol=symbol, price=price, size=size, side='Bid'))
                for price, size in book['asks']:
                    db.session.add(OrderBookEntry(symbol=symbol, price=price, size=size, side='Ask'))
            db.session.commit()
            print('Order book pre-populated with major tech stocks.')
    print(">>> Starting TradeSim Unified Server on http://127.0.0.1:5000")
    print(">>> Open this URL in your browser to launch the application.")
    socketio.run(app, host='127.0.0.1', port=5000)