from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Khai báo các biến môi trường của bạn ở đây, ví dụ kết nối Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    
    # Cấu hình để đọc file .env nếu có
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# Khởi tạo đối tượng settings để các module khác import vào dùng
settings = Settings()