from flask import Flask,render_template,request,session,redirect,url_for,flash,send_from_directory
import pymysql
from hashlib import sha1
import math
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import csv


app = Flask(__name__)
app.secret_key = 'Ama-10'

LOGIN_LOG_FILE = "logs/login_log.csv"
FORGET_LOG_FILE = "logs/forget_log.csv"

def init_csv_log(log_file):
    import os
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    if not os.path.exists(log_file):
        with open(log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'ip', 'card_number', 'status', 'failure_reason', 'user_agent'])

def log_to_csv(log_file, card_number, status, failure_reason=None):
    init_csv_log(log_file)
    if request.headers.get('X-Real-Ip'):
        real_ip = request.headers.get('X-Real-Ip')

    elif request.headers.get('X-Forwarded-For'):
        real_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        real_ip = request.remote_addr

    with open(log_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            real_ip,
            card_number,
            status,
            failure_reason or '',
            request.headers.get('User-Agent', '')
        ])

def get_db_connection():

    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='123456',
        database='library',
        cursorclass=pymysql.cursors.DictCursor
    )

    return connection

def check_out_of_due(card_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    records_sql = 'SELECT record_id, due_date, status FROM Borrow_records WHERE card_number=%s'
    reader_sql = 'SELECT status FROM Readers WHERE card_number=%s'
    cursor.execute(records_sql,(card_number,))
    records = cursor.fetchall()
    cursor.execute(reader_sql,(card_number))
    reader =cursor.fetchone()

    current_date = datetime.now().date()
    out = False
    for record in records:
        if record['due_date'] < current_date:
            if record['status'] == '借出':
                out_of_time_sql = "UPDATE Borrow_records SET status='逾期' WHERE record_id=%s"
                cursor.execute(out_of_time_sql,(record['record_id'],))

            out = True

    if out and reader['status'] == '正常':
        stop_borrow_sql = "UPDATE readers SET status='停借' WHERE card_number=%s"
        cursor.execute(stop_borrow_sql, (card_number,))

    if not out and reader['status'] == '停借':
        recover_borrow_sql = "UPDATE readers SET status='正常' WHERE card_number=%s"
        cursor.execute(recover_borrow_sql, (card_number,))

    conn.commit()
    cursor.close()
    conn.close()

def check_readers():
    conn = get_db_connection()
    cursor = conn.cursor()
    current_date = datetime.now().date()

    cursor.execute("""
           UPDATE Borrow_records 
           SET status = '逾期' 
           WHERE due_date < %s AND status = '借出'
       """, (current_date,))

    cursor.execute("""
           UPDATE Readers r
           SET r.status = '停借'
           WHERE r.status = '正常'
             AND EXISTS (
                 SELECT 1 FROM Borrow_records b
                 WHERE b.card_number = r.card_number
                   AND b.due_date < %s
                   AND b.status = '逾期'
             )
       """, (current_date,))

    cursor.execute("""
           UPDATE Readers r
           SET r.status = '正常'
           WHERE r.status = '停借'
             AND NOT EXISTS (
                 SELECT 1 FROM Borrow_records b
                 WHERE b.card_number = r.card_number
                   AND b.due_date < %s
                   AND b.status = '逾期'
             )
       """, (current_date,))

    conn.commit()
    cursor.close()
    conn.close()

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

@app.route('/')
def base():
    return render_template('base.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = sha1(request.form.get('password').encode()).hexdigest()

        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "SELECT * FROM Readers WHERE card_number=%s AND password=%s"
        cursor.execute(sql,(username,password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['loggedin'] = True
            session['card_number'] = user['card_number']
            session['username'] = user['name']
            session['is_admin'] = user['is_admin']

            log_to_csv(LOGIN_LOG_FILE, username,'SUCCESS','登录成功')
            #flash(f'欢迎回来，{user['name']}')
            return redirect(url_for('home'))
        else:
            flash('登录失败。请检查账号或密码是否正确。')
            log_to_csv(LOGIN_LOG_FILE, username, 'FAILURE', '登录失败')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('card_number',None)
    session.pop('username', None)
    session.pop('is_admin', None)
    return redirect(url_for('home'))

@app.route('/forget_password',methods=['GET','POST'])
def forget_password():

    if request.method == 'POST':
        username = request.form.get('username')
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "SELECT * FROM Readers WHERE card_number=%s"
        cursor.execute(sql, (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            log_to_csv(FORGET_LOG_FILE, username, 'FAILURE', '忘记密码')

        else:
            flash('用户不存在')

    return render_template('forget_password.html')


@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/user',methods=['GET','POST'])
def user_profile():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    card_number = session['card_number']
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM Readers WHERE card_number=%s"
    cursor.execute(sql,(card_number,))
    user = cursor.fetchone()

    if request.method == 'POST':
        new_phone = request.form.get('phone')
        new_password = request.form.get('password')
        sql_phone = "UPDATE Readers SET phone=%s WHERE card_number=%s"
        sql_password = "UPDATE Readers SET password=%s WHERE card_number=%s"

        if new_phone != user['phone']:
            cursor.execute(sql_phone,(new_phone,card_number))

        if new_password != '':
            if len(new_password) < 6:
                flash('密码长度不足')
            else:
                new_password =sha1(new_password.encode()).hexdigest()
                cursor.execute(sql_password,(new_password,card_number))
        conn.commit()
        return redirect(url_for('user_profile'))

    return render_template('personal_center.html',user=user)

@app.route('/borrow',methods=['GET'])

def search_books():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    isbn = request.args.get('isbn', '').strip()
    title = request.args.get('title', '').strip()
    author = request.args.get('author', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 10

    condition = None
    value = None
    if isbn:
        condition = "isbn"
        value = f"%{isbn}%"
    elif title:
        condition = "title"
        value = f"%{title}%"
    elif author:
        condition = "author"
        value = f"%{author}%"

    conn = get_db_connection()
    cursor = conn.cursor()

    base_sql = 'SELECT isbn, title, author, publisher, publish_time, (SELECT group_concat(category_name) FROM Categories WHERE category_code=category_code), total_copies,available_copies,location FROM Books '

    if condition:
        where = f" WHERE {condition} LIKE %s"
        count_sql = ''.join(("SELECT COUNT(*) AS total FROM Books",where))
        data_sql = base_sql + where + " LIMIT %s OFFSET %s"
        count_params = [value]
        data_params = [value, per_page, (page - 1) * per_page]
    else:
        count_sql = "SELECT COUNT(*) AS total FROM Books"
        data_sql = base_sql + " LIMIT %s OFFSET %s"
        count_params = []
        data_params = [per_page, (page - 1) * per_page]

    cursor.execute(count_sql, count_params)
    total = cursor.fetchone()['total']
    total_pages = math.ceil(total / per_page) if total > 0 else 1


    cursor.execute(data_sql, data_params)
    books = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('borrow_book.html',
                           books=books,
                           page=page,
                           total_pages=total_pages,
                           isbn=isbn,
                           title=title,
                           author=author)

@app.route('/borrow',methods=['POST'])
def borrow_operation():
    isbn = request.form.get('isbn')
    card_number = session['card_number']

    conn = get_db_connection()
    cursor = conn.cursor()
    reader_sql = 'SELECT name, status FROM Readers WHERE card_number=%s'
    cursor.execute(reader_sql,(card_number,))
    reader = cursor.fetchone()

    if reader['status'] != '正常':
        flash('该用户暂不可借阅')
        cursor.close()
        conn.close()
        return redirect(url_for('search_books'))

    else:
        update_sql = 'UPDATE Books SET available_copies = available_copies-1 WHERE isbn=%s'
        cursor.execute(update_sql,(isbn,))

        due_date = datetime.now() + timedelta(days=30)
        operator = session['username']

        insert_sql = 'INSERT INTO Borrow_records(card_number, isbn, due_date ,operator) VALUES(%s,%s,%s,%s)'
        cursor.execute(insert_sql,(card_number,isbn,due_date,operator))

        conn.commit()
        cursor.close()
        conn.close()

        flash('借阅成功！')
        return redirect(url_for('search_books'))

@app.route('/my_borrows',methods=['GET'])
def my_borrows():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    isbn = request.args.get('isbn', '').strip()
    title = request.args.get('title', '').strip()
    author = request.args.get('author', '').strip()

    page = request.args.get('page', 1, type=int)
    per_page = 10

    condition = None
    value = None
    card_number = session['card_number']

    if isbn:
        condition = "isbn"
        value = f"%{isbn}%"
    elif title:
        condition = "title"
        value = f"%{title}%"
    elif author:
        condition = "author"
        value = f"%{author}%"

    conn = get_db_connection()
    cursor = conn.cursor()

    base_sql = 'SELECT br.*, (SELECT title FROM Books b WHERE b.isbn = br.isbn) AS title FROM Borrow_records br'

    if condition:
        where = f" WHERE isbn=(SELECT b.isbn FROM Books b WHERE {condition} LIKE %s) AND card_number=%s"
        count_sql = ''.join(("SELECT COUNT(*) AS total FROM Borrow_records",where))
        data_sql = base_sql + where + " LIMIT %s OFFSET %s"
        count_params = [value, card_number]
        data_params = [value, card_number, per_page, (page - 1) * per_page]

    else:
        where = f" WHERE card_number=%s"
        count_sql = ''.join(("SELECT COUNT(*) AS total FROM Borrow_records",where))
        data_sql = base_sql + " LIMIT %s OFFSET %s"
        count_params = [card_number]
        data_params = [per_page, (page - 1) * per_page]

    cursor.execute(count_sql, count_params)
    total = cursor.fetchone()['total']
    total_pages = math.ceil(total / per_page) if total > 0 else 1


    cursor.execute(data_sql, data_params)
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('my_borrows.html', records=records, page=page, total_pages=total_pages, isbn=isbn, title=title, author=author)

@app.route('/return_book',methods=['POST'])
def return_operation():
    record_id = request.form.get('record_id')
    card_number = session['card_number']

    conn = get_db_connection()
    cursor = conn.cursor()
    reader_sql = 'SELECT name, status FROM Readers WHERE card_number=%s'
    cursor.execute(reader_sql, (card_number,))
    reader = cursor.fetchone()

    if reader['status'] not in ('正常','停借'):
        flash('该用户暂不可还书')
        cursor.close()
        conn.close()
        return redirect(url_for('my_borrows'))

    else:
        record_sql = 'SELECT isbn, status FROM Borrow_records WHERE record_id=%s'
        cursor.execute(record_sql, (record_id,))
        record = cursor.fetchone()
        isbn = record['isbn']
        operator= session['username']

        if record['status'] not in ('借出','逾期'):
            return redirect(url_for('my_borrows'))

        update_books_sql = 'UPDATE Books SET available_copies=available_copies+1 WHERE isbn=%s'
        update_records_sql = "UPDATE Borrow_records SET status='已还', return_date=NOW(), operator=%s WHERE record_id=%s"
        cursor.execute(update_books_sql,(isbn,))
        cursor.execute(update_records_sql,(operator,record_id))
        conn.commit()

        cursor.close()
        conn.close()

        check_out_of_due(card_number)

        flash('还书成功！')
        return redirect(url_for('my_borrows'))

@app.route('/renew_book',methods=['POST'])
def renew_operation():
    record_id = request.form.get('record_id')
    due_date_sql = 'SELECT due_date,renew_count FROM Borrow_records WHERE record_id=%s'
    renew_sql = 'UPDATE Borrow_records SET due_date=%s, renew_count=renew_count+1 WHERE record_id=%s'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(due_date_sql,(record_id,))
    record = cursor.fetchone()
    due_date = record['due_date']
    renew_count = record['renew_count']

    if renew_count >= 3:
        flash('续借次数已达到上限！')
        return redirect(url_for('my_borrows'))

    new_due_date = due_date + timedelta(days=30)
    cursor.execute(renew_sql,(new_due_date, record_id))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('my_borrows'))

@app.route('/add_book',methods=['GET'])
def add_book():
    categories = [('A', '马克思主义、列宁主义、毛泽东思想、邓小平理论'),
                  ('B', '哲学、宗教'),
                  ('C', '社会科学总论'),
                  ('D', '政治、法律'),
                  ('E', '军事'),
                  ('F', '经济'),
                  ('G', '文化、科学、教育、体育'),
                  ('H', '语言、文字'),
                  ('I', '文学'),
                  ('J', '艺术'),
                  ('K', '历史、地理'),
                  ('N', '自然科学总论'),
                  ('O', '数理科学和化学'),
                  ('P', '天文学、地球科学'),
                  ('Q', '生物科学'),
                  ('R', '医药、卫生'),
                  ('S', '农业科学'),
                  ('T', '工业技术'),
                  ('U', '交通运输'),
                  ('V', '航空、航天'),
                  ('X', '环境科学、安全科学'),
                  ('Z', '综合性图书')]

    return render_template('add_book.html',categories=categories)

@app.route('/add_book',methods=['POST'])
def add_operation():

    isbn = request.form.get('isbn').strip()
    title = request.form.get('title').strip()
    author = request.form.get('author').strip()
    publisher = request.form.get('publisher').strip()
    publish_time = request.form.get('publish_time').strip()
    category_code = request.form.get('category_code').strip()
    total_copies = request.form.get('total_copies').strip()
    available_copies = total_copies
    location = request.form.get('location').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    exist_sql = 'SELECT * FROM Books WHERE isbn=%s'
    cursor.execute(exist_sql,(isbn,))
    book = cursor.fetchone()

    if book:
        update_sql = 'UPDATE Books SET title=%s, author=%s, publisher=%s, publish_time=%s, category_code=%s, total_copies=%s, available_copies=%s, location=%s WHERE isbn=%s'
        cursor.execute(update_sql,(title,author,publisher,publish_time,category_code,total_copies,available_copies,location,isbn))
    else:
        add_sql = 'INSERT INTO Books(isbn, title, author, publisher, publish_time, category_code, total_copies, available_copies, location) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)'
        cursor.execute(add_sql, (isbn,title,author,publisher,publish_time,category_code,total_copies,available_copies,location))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('add_book'))

@app.route('/readers_info',methods=['GET'])
def readers_info():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    card_number = request.args.get('card_number', '').strip()
    name = request.args.get('name', '').strip()
    phone = request.args.get('phone', '').strip()

    page = request.args.get('page', 1, type=int)
    per_page = 10

    condition = None
    value = None

    if card_number:
        condition = "card_number"
        value = f"%{card_number}%"
    elif name:
        condition = "name"
        value = f"%{name}%"
    elif phone:
        condition = "phone"
        value = f"%{phone}%"

    conn = get_db_connection()
    cursor = conn.cursor()

    base_sql = 'SELECT * FROM Readers'

    if condition:
        where = f" WHERE {condition} LIKE %s"
        count_sql = ''.join(("SELECT COUNT(*) AS total FROM Readers",where))
        data_sql = base_sql + where + " LIMIT %s OFFSET %s"
        count_params = [value]
        data_params = [value, per_page, (page - 1) * per_page]

    else:
        count_sql = "SELECT COUNT(*) AS total FROM Readers"
        data_sql = base_sql + " LIMIT %s OFFSET %s"
        count_params = []
        data_params = [per_page, (page - 1) * per_page]

    cursor.execute(count_sql, count_params)
    total = cursor.fetchone()['total']
    total_pages = math.ceil(total / per_page) if total > 0 else 1


    cursor.execute(data_sql, data_params)
    readers = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('readers_info.html', readers=readers, page=page, total_pages=total_pages, card_number=card_number, name=name, phone=phone)

@app.route('/report_loss',methods=['POST'])
def loss_operation():
    card_number = request.form.get('card_number')
    reader_sql = 'SELECT status FROM Readers where card_number=%s'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(reader_sql,(card_number,))
    reader = cursor.fetchone()
    if  reader:
        if reader['status'] in ('正常','停借'):
            report_loss_sql = "UPDATE Readers SET status='挂失' WHERE card_number=%s"
            cursor.execute(report_loss_sql,(card_number,))
            conn.commit()
            cursor.close()
            conn.close()

    return redirect(url_for('readers_info'))



@app.route('/recover',methods=['POST'])
def recover_operation():
    card_number = request.form.get('card_number')
    reader_sql = 'SELECT status FROM Readers where card_number=%s'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(reader_sql, (card_number,))
    reader = cursor.fetchone()

    if reader['status'] == '挂失':
        report_loss_sql = "UPDATE Readers SET status='正常' WHERE card_number=%s"
        cursor.execute(report_loss_sql, (card_number,))
        conn.commit()
        cursor.close()
        conn.close()

    check_out_of_due(card_number)
    return redirect(url_for('readers_info'))

@app.route('/reset_password',methods=['POST'])
def reset_password():
    card_number = request.form.get('card_number')
    reader_sql = 'SELECT status FROM Readers where card_number=%s'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(reader_sql, (card_number,))
    reader = cursor.fetchone()

    if reader['status'] in ('正常', '停借'):
        card_number = request.form.get('card_number')
        reset_sql = "UPDATE Readers SET password='f7bd0b6187b5852af247bc674bb2d20345ec992c' WHERE card_number=%s"

        cursor.execute(reset_sql, (card_number))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('readers_info'))


@app.route('/cancel',methods=['POST'])
def cancel_operation():
    password = sha1(request.form.get('password').encode()).hexdigest()
    password_sql = 'SELECT password FROM Readers WHERE card_number=%s'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(password_sql,(session['card_number']))
    admin = cursor.fetchone()
    admin_password = admin['password']

    if password != admin_password:
        flash('密码错误')
        return redirect(url_for('readers_info'))

    card_number = request.form.get('card_number')
    reader_sql = 'SELECT status FROM Readers where card_number=%s'

    cursor.execute(reader_sql, (card_number,))
    reader = cursor.fetchone()
    if reader:
        if reader['status'] in ('正常', '停借'):
            cancel_sql = "UPDATE Readers SET status='注销' WHERE card_number=%s"
            cursor.execute(cancel_sql, (card_number,))

            conn.commit()
            cursor.close()
            conn.close()

    return redirect(url_for('readers_info'))

@app.route('/borrow_records',methods=['GET'])
def borrow_records():

    isbn = request.args.get('isbn', '').strip()
    title = request.args.get('title', '').strip()
    card_number = request.args.get('card_number', '').strip()

    page = request.args.get('page', 1, type=int)
    per_page = 10

    condition = None
    value = None

    if isbn:
        condition = "isbn"
        value = f"%{isbn}%"
    elif title:
        condition = "title"
        value = f"%{title}%"
    elif card_number:
        condition = "card_number"
        value = f"%{card_number}%"

    conn = get_db_connection()
    cursor = conn.cursor()

    base_sql = 'SELECT br.*, (SELECT title FROM Books b WHERE b.isbn = br.isbn) AS title FROM Borrow_records br'

    if condition:

        if condition == "isbn":
            where = " WHERE br.isbn LIKE %s"
        elif condition == "title":
            where = " WHERE br.isbn IN (SELECT isbn FROM Books WHERE title LIKE %s)"
        else:
            where = " WHERE br.card_number LIKE %s"

        count_sql = ''.join(("SELECT COUNT(*) AS total FROM Borrow_records br",where))
        data_sql = base_sql + where + " LIMIT %s OFFSET %s"
        count_params = [value,]
        data_params = [value, per_page, (page - 1) * per_page]

    else:
        count_sql = "SELECT COUNT(*) AS total FROM Borrow_records"
        data_sql = base_sql + " LIMIT %s OFFSET %s"
        count_params = []
        data_params = [per_page, (page - 1) * per_page]

    cursor.execute(count_sql, count_params)
    total = cursor.fetchone()['total']
    total_pages = math.ceil(total / per_page) if total > 0 else 1


    cursor.execute(data_sql, data_params)
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('borrow_records.html', records=records, page=page, total_pages=total_pages, isbn=isbn, title=title, card_number=card_number)


@app.route('/add_reader',methods=['GET'])
def add_reader():
    return render_template('add_reader.html')

@app.route('/add_reader',methods=['POST'])
def add_reader_operation():
    name = request.form.get('name')
    phone = request.form.get('phone')
    is_admin = request.form.get('is_admin')

    conn = get_db_connection()
    cursor = conn.cursor()
    add_sql = 'INSERT INTO Readers(name, phone, is_admin) VALUES(%s, %s, %s)'
    cursor.execute(add_sql,(name, phone, is_admin))
    conn.commit()

    cursor.close()
    conn.close()
    flash(f'成功添加读者{{name}}！')
    return redirect(url_for('add_reader'))



scheduler = BackgroundScheduler()
scheduler.add_job(func=check_readers, trigger='cron', hour=2, minute=0)
scheduler.start()

@app.errorhandler(404)

def not_found_error(error):
    return render_template('error.html', error_code=404, error_text='这里什么都没有...'), 404

@app.errorhandler(500)

def internal_server_error(error):
    return render_template('error.html', error_code=500, error_text='发生了一些错误...'), 500

if __name__ == '__main__':
    app.run(debug=True)

