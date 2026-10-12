# Sandbox tạo file cho khung chat (xem server.py). Thư viện ở đây là những gì
# script của model dùng được — sửa danh sách này thì nhớ sửa luôn SANDBOX_PROMPT
# trong api/routers/assistant.py để model biết.
FROM python:3.12-slim

# Font có dấu tiếng Việt cho PDF (reportlab) và biểu đồ (matplotlib).
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      python-docx==1.1.2 openpyxl==3.1.5 xlsxwriter==3.2.0 python-pptx==1.0.2 \
      reportlab==4.2.5 matplotlib==3.9.2 pillow==11.0.0 pandas==2.2.3

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox
WORKDIR /app
COPY server.py .
USER sandbox
CMD ["python", "-u", "server.py"]
