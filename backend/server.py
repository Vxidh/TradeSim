from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import time
import random
import os
import logging
import requests
import threading

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', "sqlite:///c:\\Users\\Admin\\Documents\\College\\PSE\\TradeSim\\backend\\tradesim.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
MATCHING_ENGINE_URL = os.environ.get('MATCHING_ENGINE_URL', 'http://127.0.0.1:9000')
ORDERBOOK_SYNC_INTERVAL = int(os.environ.get('ORDERBOOK_SYNC_INTERVAL_MS', '1000')) / 1000.0

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
    side = db.Column(db.String(8), nullable=False)

def generate_market_data():
    data, price, current_time = [], 2800.0, int(time.time() * 1000)
    for i in range(100):
        timestamp = current_time - (100 - i) * 60 * 1000
        o, h, l, c = price + random.uniform(-5, 5), 0, 0, 0
        h, l = o + random.uniform(0, 5), o - random.uniform(0, 5)
        c = random.uniform(l, h)
        data.append({"time": timestamp, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
        price = c
    return data
market_data = generate_market_data()

@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend', 'tradesim.html')

@app.route('/api/market_data')
def get_market_data():
    symbol = request.args.get('symbol', 'RELIANCE')
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
    data, current_time = [], int(time.time() * 1000)
    for i in range(100):
        timestamp = current_time - (100 - i) * 60 * 1000
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

@app.route('/api/orderbook')
def get_orderbook():
    bids = OrderBookEntry.query.filter_by(side='Bid').order_by(OrderBookEntry.price.desc()).all()
    asks = OrderBookEntry.query.filter_by(side='Ask').order_by(OrderBookEntry.price.asc()).all()
    bids_list = [(b.price, b.size) for b in bids]
    asks_list = [(a.price, a.size) for a in asks]
    return jsonify({'bids': bids_list, 'asks': asks_list})

def fetch_and_emit_orderbook_state(symbol=None):
    """
    Call C++ matching engine API:
      GET {MATCHING_ENGINE_URL}/orderbook/state            -> returns { "orderbooks": { "AAPL": {"bids": [[p,s],...],"asks":[...]}, ... } }
      GET {MATCHING_ENGINE_URL}/orderbook/state?symbol=SY  -> returns { "symbol": "SY", "bids": [...], "asks": [...] }
    On success: emit 'order_book_update' with {'symbol': <opt>, 'bids': [...], 'asks': [...] } or full map.
    """
    try:
        params = {'symbol': symbol} if symbol else {}
        resp = requests.get(f"{MATCHING_ENGINE_URL}/orderbook/state", params=params, timeout=2)
        if resp.status_code != 200:
            logging.debug("Engine orderbook-state returned %s", resp.status_code)
            return
        payload = resp.json()
        if symbol:
            bids = payload.get('bids', [])
            asks = payload.get('asks', [])
            socketio.emit('order_book_update', {'symbol': symbol, 'bids': bids, 'asks': asks})
        else:
            ob_map = payload.get('orderbooks')
            if isinstance(ob_map, dict):
                for sym, ob in ob_map.items():
                    bids = ob.get('bids', [])
                    asks = ob.get('asks', [])
                    socketio.emit('order_book_update', {'symbol': sym, 'bids': bids, 'asks': asks})
            else:
                # fallback single-book shape
                bids = payload.get('bids', [])
                asks = payload.get('asks', [])
                socketio.emit('order_book_update', {'bids': bids, 'asks': asks})
    except Exception:
        logging.debug("Unable to fetch orderbook state from matching engine", exc_info=True)
        return

def orderbook_sync_loop(stop_event):
    while not stop_event.is_set():
        fetch_and_emit_orderbook_state()
        stop_event.wait(ORDERBOOK_SYNC_INTERVAL)

@app.route('/api/order', methods=['POST'])
def place_order():
    order = request.json
    if not isinstance(order, dict):
        return jsonify({'status': 'error', 'message': 'Invalid JSON payload'}), 400
    symbol = order.get('symbol')
    side = order.get('side')
    qty = order.get('quantity')
    order_type = order.get('order_type', 'Market')  # Market, Limit, Stop, StopLimit
    stop_price = order.get('stop_price')  # optional numeric for Stop/StopLimit
    price = order.get('price')  # used for Limit / StopLimit

    if not symbol or side not in ('Buy', 'Sell') or not isinstance(qty, (int, str)):
        return jsonify({'status': 'error', 'message': 'Missing or invalid order fields (symbol, side, quantity)'}), 400
    if order_type not in ('Market', 'Limit', 'Stop', 'StopLimit'):
        return jsonify({'status': 'error', 'message': 'Unsupported order_type'}), 400

    try:
        quantity = int(qty)
        if quantity <= 0:
            return jsonify({'status': 'error', 'message': 'Quantity must be positive'}), 400
    except Exception:
        return jsonify({'status': 'error', 'message': 'Quantity must be an integer'}), 400

    logging.info("Received New Order: %s %s %s @ %s (stop=%s)", side, quantity, order_type, price or 'Market', stop_price)

    payload = {
        'symbol': symbol,
        'side': side,
        'quantity': quantity,
        'order_type': order_type,
        'price': price,
        'stop_price': stop_price
    }

    try:
        resp = requests.post(f"{MATCHING_ENGINE_URL}/match", json=payload, timeout=3)
        if resp.status_code != 200:
            logging.warning("Matching engine returned status %s, falling back to internal execution", resp.status_code)
            raise Exception("Non-200 from matching engine")
        resp_json = {}
        try:
            resp_json = resp.json()
        except Exception:
            resp_json = {}

        trades_from_engine = resp_json.get('trades') if isinstance(resp_json, dict) else None
        if trades_from_engine:
            for t in trades_from_engine:
                t_dict = {
                    'trade_id': t.get('trade_id'),
                    'symbol': t.get('symbol', symbol),
                    'price': t.get('price'),
                    'quantity': t.get('quantity'),
                    'side': t.get('side'),
                    'timestamp': t.get('timestamp')
                }
                socketio.emit('new_trade', t_dict)
        else:
            recent = Trade.query.filter_by(symbol=symbol).order_by(Trade.timestamp.desc()).limit(10).all()
            for t in reversed(recent):
                socketio.emit('new_trade', {
                    'trade_id': t.id,
                    'symbol': t.symbol,
                    'price': t.price,
                    'quantity': t.quantity,
                    'side': t.side,
                    'timestamp': t.timestamp
                })

        ob_update = resp_json.get('orderbook') if isinstance(resp_json, dict) else None
        if ob_update and isinstance(ob_update, dict):
            bids = ob_update.get('bids', [])
            asks = ob_update.get('asks', [])
            socketio.emit('order_book_update', {'symbol': symbol, 'bids': bids, 'asks': asks})
        else:
            # ensure exact engine state by querying engine for this symbol
            fetch_and_emit_orderbook_state(symbol=symbol)

        return jsonify({'status': 'success', 'message': 'Order forwarded to matching engine'}), 200

    except Exception:
        logging.exception("Error communicating with matching engine, using internal matching fallback")

        # --- INTERNAL FALLBACK: keep existing behavior so system remains functional ---
        trade_price = market_data[-1]['close'] + random.uniform(-0.5, 0.5)
        new_trade = Trade(
            symbol=symbol,
            price=round(trade_price, 2),
            quantity=quantity,
            side=side,
            timestamp=int(time.time() * 1000)
        )
        try:
            db.session.add(new_trade)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logging.exception("DB error while saving fallback trade")
            return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

        trade_dict = {
            'trade_id': new_trade.id,
            'symbol': new_trade.symbol,
            'price': new_trade.price,
            'quantity': new_trade.quantity,
            'side': new_trade.side,
            'timestamp': new_trade.timestamp
        }
        socketio.emit('new_trade', trade_dict)

        try:
            if side == 'Buy':
                best_ask = OrderBookEntry.query.filter_by(side='Ask').order_by(OrderBookEntry.price.asc()).first()
                if best_ask:
                    best_ask.size = max(0, best_ask.size - quantity)
                    if best_ask.size == 0:
                        db.session.delete(best_ask)
                    db.session.commit()
            elif side == 'Sell':
                best_bid = OrderBookEntry.query.filter_by(side='Bid').order_by(OrderBookEntry.price.desc()).first()
                if best_bid:
                    best_bid.size = max(0, best_bid.size - quantity)
                    if best_bid.size == 0:
                        db.session.delete(best_bid)
                    db.session.commit()
        except Exception:
            db.session.rollback()
            logging.exception("DB error while updating fallback order book")
            return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

        bids = OrderBookEntry.query.filter_by(side='Bid').order_by(OrderBookEntry.price.desc()).all()
        asks = OrderBookEntry.query.filter_by(side='Ask').order_by(OrderBookEntry.price.asc()).all()
        bids_list = [(b.price, b.size) for b in bids]
        asks_list = [(a.price, a.size) for a in asks]
        socketio.emit('order_book_update', {'bids': bids_list, 'asks': asks_list})
        return jsonify({'status': 'success', 'message': 'Order executed by internal fallback'}), 200

@socketio.on('connect')
def handle_connect():
    logging.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logging.info('Client disconnected')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if OrderBookEntry.query.count() == 0:
            tech_stocks = {
                'AAPL': {'bids': [(170.10, 200), (169.80, 150), (169.50, 100)], 'asks': [(170.50, 180), (170.80, 120), (171.00, 80)]},
                'MSFT': {'bids': [(330.20, 180), (329.90, 140), (329.50, 90)], 'asks': [(330.60, 160), (330.90, 110), (331.20, 70)]},
                'GOOG': {'bids': [(2800.10, 100), (2799.80, 80), (2799.50, 60)], 'asks': [(2801.50, 90), (2802.00, 70), (2802.50, 50)]},
                'AMZN': {'bids': [(3400.10, 90), (3399.80, 70), (3399.50, 50)], 'asks': [(3401.50, 80), (3402.00, 60), (3402.50, 40)]},
                'META': {'bids': [(320.10, 200), (319.80, 150), (319.50, 100)], 'asks': [(320.50, 180), (320.80, 120), (321.00, 80)]},
                'TSLA': {'bids': [(700.10, 200), (699.80, 150), (699.50, 100)], 'asks': [(701.50, 180), (701.80, 120), (702.00, 80)]},
                'RELIANCE': {'bids': [(2850.10, 200), (2849.80, 150), (2849.50, 100)], 'asks': [(2851.50, 180), (2852.00, 120), (2852.50, 80)]}
            }
            for symbol, book in tech_stocks.items():
                for price, size in book['bids']:
                    db.session.add(OrderBookEntry(symbol=symbol, price=price, size=size, side='Bid'))
                for price, size in book['asks']:
                    db.session.add(OrderBookEntry(symbol=symbol, price=price, size=size, side='Ask'))
            db.session.commit()
    logging.info(">>> Starting TradeSim Unified Server on http://127.0.0.1:5000")
    logging.info(">>> Open this URL in your browser to launch the application.")
    stop_event = threading.Event()
    sync_thread = threading.Thread(target=orderbook_sync_loop, args=(stop_event,), daemon=True)
    sync_thread.start()
    try:
        socketio.run(app, host='127.0.0.1', port=5000)
    finally:
        stop_event.set()