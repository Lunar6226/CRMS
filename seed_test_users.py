"""One-off script to add 10 test citizen accounts for manual testing."""
from app import app, db, User

TEST_USERS = [
    {'full_name': 'Grace Mushi', 'email': 'grace.mushi@gmail.com', 'phone': '+255700001001'},
    {'full_name': 'Emmanuel Kileo', 'email': 'emmanuel.kileo@gmail.com', 'phone': '+255700001002'},
    {'full_name': 'Neema Shayo', 'email': 'neema.shayo@gmail.com', 'phone': '+255700001003'},
    {'full_name': 'Baraka Mnyamani', 'email': 'baraka.mnyamani@gmail.com', 'phone': '+255700001004'},
    {'full_name': 'Fatuma Rajabu', 'email': 'fatuma.rajabu@gmail.com', 'phone': '+255700001005'},
    {'full_name': 'Joseph Mwakalinga', 'email': 'joseph.mwakalinga@gmail.com', 'phone': '+255700001006'},
    {'full_name': 'Amina Chacha', 'email': 'amina.chacha@gmail.com', 'phone': '+255700001007'},
    {'full_name': 'Daniel Mrema', 'email': 'daniel.mrema@gmail.com', 'phone': '+255700001008'},
    {'full_name': 'Rehema Kimaro', 'email': 'rehema.kimaro@gmail.com', 'phone': '+255700001009'},
    {'full_name': 'Peter Ndosi', 'email': 'peter.ndosi@gmail.com', 'phone': '+255700001010'},
]
TEST_PASSWORD = 'TestPass@123'

with app.app_context():
    db.create_all()
    for u in TEST_USERS:
        if User.query.filter_by(email=u['email']).first():
            continue
        user = User(full_name=u['full_name'], email=u['email'], phone=u['phone'],
                    role='citizen', email_verified=True)
        user.set_password(TEST_PASSWORD)
        db.session.add(user)
    db.session.commit()
    print(f"Done. {len(TEST_USERS)} test users ensured (password for all: {TEST_PASSWORD})")
