from server import app, db
from models import Product, ProductVariant


with app.app_context():
    print("Выберите действие:\n1. Добавить товар\n2.Изменить товар\n3.Удалить товар")
    inp = input("> ")
    while inp.lower() != "q":
        if inp == "1":
            name = input("Введите имя: ")
            article = input("Введите артикул: ")
            category = input("hat/cap: ")
            price = float(input("Введите цену: "))
            main_image = input("Введите путь до картинки: ")

            product = Product(
                name=name,
                article=article,
                category=category,
                price=price,
                main_image=main_image
                )

            db.session.add(product)
            db.session.commit()

            ifVariants = input("Доп. варианты (y/n): ")
            while ifVariants.lower() != "n":
                size = input("Размер: ")
                color = input("Цвет: ")
                stock = int(input("В наличии: "))
                image = input("Введите путь до картинки: ")

                variant = ProductVariant(
                    product_id=product.id,
                    size=size,
                    color=color,
                    stock=stock,
                    image=image
                )

                db.session.add(variant)
                db.session.commit()

                ifVariants = input("Доп. варианты (y/n): ")

        print("Выберите действие:\n1. Добавить товар\n2.Изменить товар\n3.Удалить товар")
        inp = input("> ")