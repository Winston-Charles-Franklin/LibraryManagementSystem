create database if not exists Library ;

use Library;

create table if not exists Categories(
    category_id int primary key auto_increment,
    category_code varchar(10) unique not null,
    category_name varchar(100) unique not null,
    parent_id int default 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

create table if not exists Books(
    isbn varchar(25) primary key not null,
    title varchar(200) not null,
    author varchar(100),
    publisher varchar(100),
    publish_time year,
    category_code varchar(10),
    total_copies int default 1,
    available_copies int default 1,
    location varchar(50),
    foreign key (category_code) references Categories(category_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

create table if not exists Readers(
    card_number BIGINT primary key not null auto_increment,
    name varchar(20) not null,
    phone varchar(20),
    reg_time timestamp default current_timestamp,
    status enum('正常','停借','挂失','注销') default '正常',
    password varchar(255) default 'f7bd0b6187b5852af247bc674bb2d20345ec992c',
    is_admin bool default false
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

create table if not exists Borrow_records(
    record_id int primary key auto_increment,
    card_number BIGINT,
    isbn varchar(20),
    borrow_date datetime default current_timestamp,
    due_date date not null,
    return_date datetime,
    renew_count int default 0,
    status enum('借出','已还','逾期') default '借出',
    operator varchar(50),
    foreign key (card_number) references Readers(card_number),
    foreign key (isbn) references Books(isbn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


insert into Readers(card_number, name, phone, password, is_admin) values('3501032720210001','Ama-10','13800005555','7c4a8d09ca3762af61e59520943dc26494f8941b',TRUE);

insert into Categories(category_code, category_name) values
('A', '马克思主义、列宁主义、毛泽东思想、邓小平理论'),
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
('Z', '综合性图书');

insert into Books(isbn, title, author, publisher, publish_time, category_code, total_copies, available_copies, location) values
('978-7-111-23655-9', '朝花夕拾', '鲁迅', '机械工业出版社', '2008', 'I', '5', '5', '1-5-24'),
('978-7-5366-9293-0', '三体', '刘慈欣', '重庆出版社', '2008', 'I', '3', '2', '1-5-22'),
('CN:13031.915', '初等数论-1', '陈景润', '科学出版社', '1978', 'O', '6', '3', '2-3-15');
