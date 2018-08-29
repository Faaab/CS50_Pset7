from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

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

    # Retrieve user portfolio from database
    stockrows = db.execute("SELECT * FROM portfolios WHERE user = :user_id",
                           user_id=session["user_id"])

    # After retrieval, stockrows stores: user who owns it, stock symbol, amount of shares owned.
    # Now lookup that stock and add to stockrows: stock name, current price, total value of shares owned.
    for i in range(len(stockrows)):
        stock = lookup(stockrows[i]['symbol'])
        stockrows[i]['name'] = stock["name"]
        stockrows[i]['current_price'] = stock["price"]
        stockrows[i]['total'] = stockrows[i]['shares'] * stock["price"]

    # Retrieve from database: amount of cash owned by user.
    rows = db.execute("SELECT cash FROM users WHERE id = :user_id",
                      user_id=session["user_id"])
    usercash = rows[0]['cash']

    # Calculate grand total of all user's holdings
    grandtotal = 0
    for i in range(len(stockrows)):
        grandtotal += stockrows[i]['total']

    grandtotal += usercash

    # convert price, total, usercash and grandtotal into USD
    for i in range(len(stockrows)):
        stockrows[i]['current_price'] = usd(stockrows[i]['current_price'])
        stockrows[i]['total'] = usd(stockrows[i]['total'])

    usercash = usd(usercash)
    grandtotal = usd(grandtotal)

    return render_template("index.html", stockrows=stockrows, grandtotal=grandtotal, usercash=usercash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        # check if all fields were filled in
        if not request.form.get("symbol"):
            return apology("missing symbol")

        elif not request.form.get("shares"):
            return apology("missing shares")

        # check whether 'shares' field only contains digits (if not, input is either a float or a string, which are not supported)
        num_digits = sum(c.isdigit() for c in request.form.get("shares"))
        if num_digits != len(request.form.get("shares")):
            return apology("'shares' must be a positive integer")

        # store result of lookup(symbol) in dict
        stock = lookup(request.form.get("symbol"))

        # if stock is not found, apologize
        if not stock:
            return apology("invalid symbol")

        # check if user has enough cash; if not, apologize
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=session["user_id"])
        shares = int(request.form.get("shares"))
        buy_price = stock["price"] * shares
        usercash = rows[0]['cash']
        if buy_price > usercash:
            return apology("can't afford")

        # Save transaction in history table
        result = db.execute("INSERT INTO history (user, price, symbol, buysell, shares, amount) VALUES (:user_id, :price, :symbol, 'buy', :share_num, :price * :share_num)",
                            user_id=session["user_id"], price=stock["price"], symbol=stock["symbol"], share_num=shares)

        # Find out whether user has stock of this type. If so, update portfolio, if not, insert into portfolio.
        rows = db.execute("SELECT * FROM portfolios WHERE user = :user_id AND symbol = :buysymbol",
                          user_id=session["user_id"], buysymbol=stock["symbol"])
        if len(rows) < 1:
            # user has no stock of this type yet
            result = db.execute("INSERT INTO portfolios (user, symbol, shares) VALUES (:user_id, :symbol, :shares)",
                                user_id=session["user_id"], symbol=stock["symbol"], shares=request.form.get("shares"))

        else:
            # user already has stock of this type
            result = db.execute("UPDATE portfolios SET shares = shares + :new_shares WHERE user = :user_id AND symbol = :buysymbol",
                                new_shares=shares, user_id=session["user_id"], buysymbol=stock["symbol"])

        # update cash
        result = db.execute("UPDATE users SET cash = cash - :price WHERE id = :user_id",
                            price=buy_price, user_id=session["user_id"])

        return redirect("/")

    else:
        # user reached route via GET
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # get from 'history' database: for every transaction by user: buysell, symbol, price (of purchase/sale), number of shares, total, datetime.
    userhistory = db.execute("SELECT symbol, buysell, shares, price, amount, datetime FROM history WHERE user = :user_id",
                             user_id=session["user_id"])

    # format price and amount of each row to USD
    for i in range(len(userhistory)):
        userhistory[i]['price'] = usd(userhistory[i]['price'])
        userhistory[i]['amount'] = usd(userhistory[i]['amount'])

    # Pass all this info to HTML/Jinja template
    return render_template("history.html", userhistory=userhistory)


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


@app.route("/options", methods=["GET", "POST"])
@login_required
def options():
    """Let user change password or add cash to account"""
    if request.method == "POST":

        # path for changing password
        if request.form.get("submitpass"):
            # check if form was filled in correctly
            if not request.form.get("password"):
                return apology("missing password")

            if request.form.get("password") != request.form.get("confirmation"):
                return apology("passwords do not match")

            # check if password is long enough, and has at least one digit, letter and symbol
            if len(request.form.get("password")) <= 8:
                return apology("password must be at least 9 characters")

            sum_letters = sum(c.isalpha() for c in request.form.get("password"))
            if sum_letters < 1:
                return apology("password must contain at least 1 letter, digit and symbol")

            sum_digits = sum(c.isdigit() for c in request.form.get("password"))
            if sum_digits < 1:
                return apology("password must contain at least 1 letter, digit and symbol")

            if sum_letters + sum_digits == len(request.form.get("password")):
                return apology("password must contain at least 1 letter, digit and symbol")

            # update database with hashed new password
            db.execute("UPDATE users SET hash = :hash WHERE id = :user_id",
                       hash=generate_password_hash(request.form.get("password")), user_id=session["user_id"])

            # let user know that password was changed
            return render_template("pass_changed.html")

        # path for adding cash
        elif request.form.get("submitcash"):
            db.execute("UPDATE users SET cash = cash + :addcash WHERE id = :user_id",
                       addcash=request.form.get("cash"), user_id=session["user_id"])

            return redirect("/")

    else:
        # user reached route via GET; show password change form
        return render_template("options.html")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        # look up stock price
        if not request.form.get("symbol"):
            return apology("missing symbol")

        # store result of lookup(symbol) in dict
        stock = lookup(request.form.get("symbol"))

        # if stock is not found, apologize
        if not stock:
            return apology("invalid symbol")

        # if stock is valid, return ("/quoted.html") with values plugged in
        return render_template("/quoted.html", name=stock["name"], price=usd(stock["price"]), symbol=stock["symbol"])

    else:
        # user reached route via GET; display form to find quote
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Missing username!")

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("Missing password!")

        # Ensure password confirmation was submitted
        if not request.form.get("confirmation"):
            return apology("Missing password confirmation!")

        # Check if passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match!")

        # check if password is long enough, and has at least one digit, letter and symbol
#        if len(request.form.get("password")) <= 8:
#            return apology("password must be at least 9 characters")

#        sum_letters = sum(c.isalpha() for c in request.form.get("password"))
#        if sum_letters < 1:
#            return apology("password must contain at least 1 letter, digit and symbol")

#        sum_digits = sum(c.isdigit() for c in request.form.get("password"))
#        if sum_digits < 1:
#            return apology("password must contain at least 1 letter, digit and symbol")

#        if sum_letters + sum_digits == len(request.form.get("password")):
#            return apology("password must contain at least 1 letter, digit and symbol")

        # Insert user into database, along with hashed password. Note: result stores user's id (since db.execute-INSERT commands return resulting primary key)
        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                            username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        # Check if insertion failed. If it did, username was probably already in use.
        if not result:
            return apology("Username already exists")

        # log user in automatically
        session["user_id"] = result

        # Redirect user to home page
        return redirect("/")

    else:
        # user reached route via GET
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":
        # check if form was submitted correctly
        if not request.form.get("symbol"):
            return apology("missing symbol")

        if not request.form.get("shares"):
            return apology("missing shares")

        # look up how many shares of the submitted type the user owns
        sharerows = db.execute("SELECT * FROM portfolios WHERE user = :user_id AND symbol = :sellsymbol",
                               user_id=session["user_id"], sellsymbol=request.form.get("symbol"))
        shares_owned = sharerows[0]['shares']

        # if user wants to sell more than s/he has, apologize
        if int(request.form.get("shares")) > shares_owned:
            return apology("too many shares")

        # if user wants to sell acceptable amount, lookup stock and update history
        stock = lookup(request.form.get("symbol"))

        db.execute("INSERT INTO history (user, price, symbol, buysell, shares, amount) VALUES (:user_id, :price, :symbol, 'sell', :share_num, :price * :share_num)",
                   user_id=session["user_id"], price=stock["price"], symbol=stock["symbol"], share_num=request.form.get("shares"))

        # if user wants to sell all shares of this tock s/he owns, DELETE FROM portfolio
        if int(request.form.get("shares")) == shares_owned:
            db.execute("DELETE FROM portfolios WHERE user = :user_id AND symbol = :sellsymbol",
                       user_id=session["user_id"], sellsymbol=request.form.get("symbol"))

        # if user does not want to sell all shares of this stock, UPDATE portfolio
        else:
            db.execute("UPDATE portfolios SET shares = shares - :share_num WHERE user = :user_id AND symbol = :sellsymbol",
                       share_num=request.form.get("shares"), user_id=session["user_id"], sellsymbol=stock["symbol"])

        # update user's cash
        db.execute("UPDATE users SET cash = cash + :share_num * :price",
                   share_num=request.form.get("shares"), price=stock["price"])

        # show user to index
        return redirect("/")

    else:
        # user reached route via GET
        # retrieve symbols of all stocks in user's portfolio
        portrows = db.execute("SELECT symbol FROM portfolios WHERE user = :user_id",
                              user_id=session["user_id"])

        # display form to user, rendered dynamically based on stocks in their portfolio
        return render_template("sell.html", portrows=portrows)


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
