# Sử dụng Python base image
FROM python:3.9-slim-buster

# Đặt thư mục làm việc trong container
WORKDIR /app

# Sao chép requirements.txt và cài đặt dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Sao chép code ứng dụng
COPY . .

# Khai báo cổng mà ứng dụng sẽ lắng nghe (Cloud Run sẽ cung cấp biến môi trường PORT)
ENV PORT 8080

# Chạy ứng dụng Flask
# Gunicorn là một WSGI server được khuyến nghị cho production
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app