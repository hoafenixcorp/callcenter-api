# Sử dụng Python base image
FROM python:3.9-slim-buster

# Đặt thư mục làm việc trong container
WORKDIR /app

# Sao chép requirements.txt và cài đặt dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Sao chép code ứng dụng
COPY . .

# Khai báo cổng mà ứng dụng sẽ lắng nghe
ENV PORT 8080

# Chạy ứng dụng FastAPI với uvicorn
CMD exec uvicorn main:app --host 0.0.0.0 --port $PORT