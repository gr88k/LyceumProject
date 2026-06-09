import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Данные авторизации СОТРУДНИКА (того, у кого есть доступ)
EMPLOYEE_EMAIL = 'chav1975@urbanpeakshop.ru'
EMPLOYEE_APP_PASSWORD = 'wgygdukrwlqpnlsg'  # Ваш личный пароль приложения

# Данные ОБЩЕГО ящика, от имени которого отправляем
SHARED_EMAIL = 'orders@urbanpeakshop.ru'
RECEIVER_EMAIL = 'chernokozhikhivan@gmail.com'

# Формирование письма
msg = MIMEMultipart()
# ВАЖНО: В заголовке From пишем ОБЩИЙ адрес, получатель увидит именно его
msg['From'] = SHARED_EMAIL
msg['Sender'] = EMPLOYEE_EMAIL
msg['To'] = RECEIVER_EMAIL
msg['Subject'] = 'Письмо из общего ящика компании'

body = 'Здравствуйте! Данный ответ отправлен с общей корпоративной почты.'
msg.attach(MIMEText(body, 'plain', 'utf-8'))

try:
    # Подключаемся к SMTP под учетными данными сотрудника
    with smtplib.SMTP_SSL('smtp.yandex.ru', 465) as server:
        server.login(EMPLOYEE_EMAIL, EMPLOYEE_APP_PASSWORD)
        
        # Передаем объект сообщения. Яндекс проверит права сотрудника 
        # на ящик SHARED_EMAIL и выполнит отправку
        server.send_message(msg)
        print(f'Письмо успешно отправлено от имени {SHARED_EMAIL}!')
        
except smtplib.SMTPDataError as e:
    print(f'Ошибка Яндекса (возможно, нет прав на отправку от имени этого ящика): {e}')
except Exception as e:
    print(f'Произошла ошибка: {e}')
