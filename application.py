import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Ensure environment variable is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get data from buy table
    buy_rows = db.execute("SELECT * FROM buy WHERE fkey = :user_id", user_id=session["user_id"])

    # Initialise variables and array list
    i = 0
    share_value = 0
    symbols = []
    shares = []
    prices = []
    totals = []

    # Loop through each row of the table and input to arrays
    for row in buy_rows:
        i = i + 1
        symbol = row["symbol"]
        share = row["share"]
        quote = lookup(symbol)
        if not quote == None:
            price = quote["price"]
            total = share * price
            share_value = share_value + total
            symbols.append(symbol)
            shares.append(share)
            prices.append(usd(price))
            totals.append(usd(total))

    # Get cash value from users table
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash_cash = cash[0]["cash"]

    # Calculate the total cash
    overall = cash_cash + share_value

    return render_template("index.html", i=i, symbols=symbols, shares=shares, prices=prices, totals=totals,
                           total=usd(cash_cash), overall=usd(overall))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)

        # Ensure symbol was valid
        elif lookup(request.form.get("symbol")) == None:
            return apology("invalid symbol", 400)

        # Ensure share was submitted
        elif not request.form.get("shares"):
            return apology("missing share", 400)

        # Ensure share was valid
        try:
            typed_share = int(request.form.get("shares"))
        except ValueError:
            return apology("invalid share", 400)

        if not int(request.form.get("shares")) >= 1:
            return apology("invalid share", 400)

        # Get the now price of the symbol
        quote = lookup(request.form.get("symbol"))
        new_share = int(request.form.get("shares"))

        price = quote["price"]
        buy_symbol = quote["symbol"]

        # Ensure sufficient cash to buy
        user_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])

        cash = user_cash[0]["cash"]

        if new_share * price > cash:
            apology("can`t afford", 400)
        else:

            # Check if the symbol is in the buy table
            existing_symbols = db.execute("SELECT count(*) FROM buy WHERE fkey = :user_id and symbol = :symbol",
                                          user_id=session["user_id"], symbol=buy_symbol)

            # Insert new row if no exists
            if existing_symbols[0]["count(*)"] == 0:
                db.execute("INSERT INTO buy (fkey, symbol, share) VALUES (:nfkey, :nsymbol, :nshare)",
                           nfkey=session["user_id"], nsymbol=quote["symbol"], nshare=new_share)
            else:

                # Update current row if exists
                db.execute("UPDATE buy SET share = :vshare WHERE fkey = :user_id and symbol = :symbol",
                           vshare=existing_symbols[0]["count(*)"] + new_share, user_id=session["user_id"],
                           symbol=buy_symbol)

            # Update cash
            db.execute("UPDATE users SET cash = :new_cash WHERE id = :user_id",
                       user_id=session["user_id"], new_cash=cash - new_share * price)

            # Update history
            db.execute("INSERT INTO history (fkey, symbol, price, share, time) VALUES (:nfkey, :nsymbol, :nprice, :nshare, :ntime)",
                       nfkey=session["user_id"], nsymbol=quote["symbol"], nprice=usd(price), nshare=new_share, ntime=str(datetime.now())[:19])

            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT * FROM history WHERE fkey = :user_id", user_id=session["user_id"])

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # User reached route via POST (as by submitting a symbol via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)
        else:
            quote = lookup(request.form.get("symbol"))

            # Ensure symbol was valid
            if quote == None:
                return apology("invalid symbol", 400)
            else:
                return render_template("quoted.html", symbol=quote["symbol"], price=usd(quote["price"]))

    # User reached input quote page via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password again", 400)

        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords don`t match", 400)

        existing_rows = db.execute("SELECT * FROM users WHERE username = :username",
                                   username=request.form.get("username"))

        if len(existing_rows) != 0:
            return apology("username taken", 400)

        # Query database for username
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                   username=request.form.get("username"), password=generate_password_hash(request.form.get("password")))

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # Redirect user to home page
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    symbols = db.execute("SELECT DISTINCT symbol FROM buy WHERE fkey = :user_id", user_id=session["user_id"])

    if request.method == "POST":
        selected_symbol = request.form.get("symbol")

        # Ensure valid share
        try:
            input_share = int(request.form.get("shares"))
        except ValueError:
            return apology("invalid share", 400)

        # Check input share is no more than owned
        owned_share = db.execute("SELECT share FROM buy WHERE fkey = :user_id AND symbol = :owned_symbols",
                                 user_id=session["user_id"], owned_symbols=selected_symbol)

        if input_share > owned_share[0]["share"]:
            return apology("too many shares", 400)

        # Check for valid symbol
        current_quote = lookup(selected_symbol)
        if not current_quote == 0:
            current_price = current_quote["price"]

        # Get the number of share if it`s sold
        current_share = owned_share[0]["share"] - input_share

        # Delete if left share is 0 and update if not
        if current_share == 0:
            db.execute("DELETE FROM buy WHERE symbol = :symbol", symbol=selected_symbol)
        else:
            db.execute("UPDATE buy SET share = :share WHERE fkey = :user_id AND symbol = :symbol",
                       share=current_share, user_id=session["user_id"], symbol=selected_symbol)

        # Get cash from the database
        user_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = user_cash[0]["cash"]

        # Update cash
        db.execute("UPDATE users SET cash = :new_cash WHERE id = :user_id",
                   user_id=session["user_id"], new_cash=cash + input_share * current_price)

        # Update history
        db.execute("INSERT INTO history (fkey, symbol, price, share, time) VALUES (:nfkey, :nsymbol, :nprice, :nshare, :ntime)",
                   nfkey=session["user_id"], nsymbol=selected_symbol, nprice=usd(current_price), nshare=input_share * (-1), ntime=str(datetime.now())[:19])

        return redirect("/")
    else:
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
