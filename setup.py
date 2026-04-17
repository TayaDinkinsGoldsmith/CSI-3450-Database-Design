import mysql.connector
import os
from dotenv import load_dotenv
from security_utils import hash_password

load_dotenv()

def init_db():

    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS")
        )
        cursor = conn.cursor()
        
        db_name = os.getenv('DB_NAME', 'IndianaHotel')
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        cursor.execute(f"USE {db_name}")

        # Order respects foreign keys.
        tables = {
            "ZIP": """
                CREATE TABLE IF NOT EXISTS ZIP (
                    ZIP_CODE VARCHAR(10) PRIMARY KEY,
                    ZIP_CITY VARCHAR(50),
                    ZIP_STATE CHAR(2)
                )""",

            "ROOMTYPE": """
                CREATE TABLE IF NOT EXISTS ROOMTYPE (
                    RTYPE_ID INT PRIMARY KEY AUTO_INCREMENT,
                    RTYPE_CODE VARCHAR(10),
                    RTYPE_NAME VARCHAR(50),
                    RTYPE_PRICE DECIMAL(10,2),
                    RTYPE_CAP INT
                )""",

            "CLIENT": """
                CREATE TABLE IF NOT EXISTS CLIENT (
                    CLIENT_ID INT PRIMARY KEY AUTO_INCREMENT,
                    CLIENT_FNAME VARCHAR(50),
                    CLIENT_LNAME VARCHAR(50),
                    CLIENT_DOB DATE,
                    CLIENT_EMAIL VARCHAR(100),
                    CLIENT_PASSWORD VARCHAR(255),
                    CLIENT_PHONE VARCHAR(15),
                    CLIENT_STREET VARCHAR(100),
                    ZIP_CODE VARCHAR(10),
                    FOREIGN KEY (ZIP_CODE) REFERENCES ZIP(ZIP_CODE)
                )""",

            "EMPLOYEE": """
                CREATE TABLE IF NOT EXISTS EMPLOYEE (
                    EMP_ID INT PRIMARY KEY AUTO_INCREMENT,
                    EMP_FNAME VARCHAR(50),
                    EMP_LNAME VARCHAR(50),
                    EMP_ROLE VARCHAR(20),
                    EMP_EMAIL VARCHAR(100),
                    EMP_PASSWORD VARCHAR(255)
                )""",

            "ROOM": """
                CREATE TABLE IF NOT EXISTS ROOM (
                    ROOM_ID INT PRIMARY KEY AUTO_INCREMENT,
                    RTYPE_ID INT,
                    ROOM_NUMBER INT,
                    ROOM_STATUS VARCHAR(20),
                    FOREIGN KEY (RTYPE_ID) REFERENCES ROOMTYPE(RTYPE_ID)
                )""",

            "PAYMENT": """
                CREATE TABLE IF NOT EXISTS PAYMENT (
                    PAY_ID INT PRIMARY KEY AUTO_INCREMENT,
                    CLIENT_ID INT,
                    PAY_PROVIDER VARCHAR(20),
                    PAY_LAST4 CHAR(4),
                    PAY_DEFAULT TINYINT,
                    FOREIGN KEY (CLIENT_ID) REFERENCES CLIENT(CLIENT_ID)
                )""",

            "RESERVATION": """
                CREATE TABLE IF NOT EXISTS RESERVATION (
                    RES_ID INT PRIMARY KEY AUTO_INCREMENT,
                    CLIENT_ID INT,
                    ROOM_ID INT,
                    RES_DATE DATETIME,
                    RES_CHECKIN DATE,
                    RES_CHECKOUT DATE,
                    RES_QUOTED_RATE DECIMAL(10,2),
                    RES_STATUS VARCHAR(20),
                    FOREIGN KEY (CLIENT_ID) REFERENCES CLIENT(CLIENT_ID),
                    FOREIGN KEY (ROOM_ID) REFERENCES ROOM(ROOM_ID)
                )""",

            "HOUSEKEEPINGLOG": """
                CREATE TABLE IF NOT EXISTS HOUSEKEEPINGLOG (
                    LOG_ID INT PRIMARY KEY AUTO_INCREMENT,
                    ROOM_ID INT,
                    EMP_ID INT,
                    LOG_DATE DATETIME,
                    LOG_ACTION VARCHAR(50),
                    LOG_NOTE TEXT,
                    FOREIGN KEY (ROOM_ID) REFERENCES ROOM(ROOM_ID),
                    FOREIGN KEY (EMP_ID) REFERENCES EMPLOYEE(EMP_ID)
                )"""
        }

        for name, ddl in tables.items():
            cursor.execute(ddl)
            print(f"Table '{name}' verified/created.")

        # Ensure password columns exist in case schema was created earlier.
        cursor.execute("SHOW COLUMNS FROM CLIENT LIKE 'CLIENT_PASSWORD'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE CLIENT ADD COLUMN CLIENT_PASSWORD VARCHAR(255)")
        cursor.execute("SHOW COLUMNS FROM EMPLOYEE LIKE 'EMP_PASSWORD'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE EMPLOYEE ADD COLUMN EMP_PASSWORD VARCHAR(255)")

        cursor.execute(
            "INSERT IGNORE INTO ZIP VALUES "
            "('48309', 'Rochester', 'MI'), ('46204', 'Indianapolis', 'IN')"
        )

        cursor.execute(
            "INSERT IGNORE INTO ROOMTYPE (RTYPE_ID, RTYPE_CODE, RTYPE_NAME, RTYPE_PRICE, RTYPE_CAP) VALUES "
            "(1, 'KNG', 'King Suite', 150.00, 2), (2, 'DBL', 'Double Queen', 120.00, 4)"
        )

        manager_pw = hash_password("Password123!")
        housekeeper_pw = hash_password("Password123!")
        employee_pw = hash_password("Password123!")
        client_pw = hash_password("Password123!")
        cursor.execute(
            "INSERT IGNORE INTO EMPLOYEE (EMP_ID, EMP_FNAME, EMP_LNAME, EMP_ROLE, EMP_EMAIL, EMP_PASSWORD) VALUES "
            "(1, 'John', 'Doe', 'Manager', 'john.doe@example.com', %s), "
            "(2, 'Jane', 'Smith', 'Housekeeper', 'jane.smith@example.com', %s), "
            "(3, 'Alex', 'Turner', 'Front Desk', 'alex.turner@example.com', %s)",
            (manager_pw, housekeeper_pw, employee_pw),
        )

        cursor.execute(
            """
            INSERT IGNORE INTO CLIENT
                (CLIENT_ID, CLIENT_FNAME, CLIENT_LNAME, CLIENT_DOB, CLIENT_EMAIL, CLIENT_PASSWORD, CLIENT_PHONE, CLIENT_STREET, ZIP_CODE)
            VALUES
                (1, 'Taylor', 'Guest', '1995-06-15', 'taylor.guest@example.com', %s, '2485551111', '123 Main Street', '46204')
            """,
            (client_pw,),
        )

        cursor.execute(
            "INSERT IGNORE INTO ROOM (ROOM_ID, RTYPE_ID, ROOM_NUMBER, ROOM_STATUS) VALUES "
            "(1, 1, 101, 'Available'), "
            "(2, 2, 102, 'Available'), "
            "(3, 1, 103, 'Available'), "
            "(4, 2, 104, 'Available'), "
            "(5, 1, 105, 'Available'), "
            "(6, 2, 106, 'Available'), "
            "(7, 1, 107, 'Available'), "
            "(8, 2, 108, 'Available'), "
            "(9, 1, 109, 'Available'), "
            "(10, 2, 110, 'Available')"
        )

        cursor.execute(
            "INSERT IGNORE INTO HOUSEKEEPINGLOG "
            "(LOG_ID, ROOM_ID, EMP_ID, LOG_DATE, LOG_ACTION, LOG_NOTE) VALUES "
            "(1, 2, 2, '2025-01-15 10:00:00', 'Service requested', 'Strip beds and restock amenities')"
        )

        conn.commit()
        print("--- Indiana Hotel Database Setup Complete ---")

    except Exception as e:
        print(f"CRITICAL ERROR during DB Setup: {e}")

    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    init_db()
