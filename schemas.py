from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator, model_validator


class RoleName(str, Enum):
    ADMIN = 'ADMIN'
    LANDLORD = 'LANDLORD'


class UserStatus(str, Enum):
    ACTIVE = 'ACTIVE'
    LOCKED = 'LOCKED'


def normalized_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError('Họ tên không được trống.')
    return value


def normalized_phone(value: str | None) -> str | None:
    import re
    if value is None or value == '':
        return None
    value = value.strip()
    if not re.fullmatch(r'\+?\d{8,15}', value, flags=re.ASCII):
        raise ValueError('SĐT cần 8–15 chữ số, có thể bắt đầu bằng +.')
    return value


def ascii_email(value: str) -> str:
    value = str(value).lower()
    if len(value) > 255 or not value.isascii():
        raise ValueError('Email tối đa 255 ký tự ASCII theo cột VARCHAR hiện có.')
    return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    identifier: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None  # Tương thích client cũ dùng email.
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def login_identifier(self):
        if (self.identifier is None) == (self.email is None):
            raise ValueError('Nhập identifier (email/SĐT) hoặc email, không nhập cả hai.')
        value = (self.identifier if self.identifier is not None else str(self.email)).strip()
        if '@' in value:
            from pydantic import TypeAdapter
            self.identifier = ascii_email(TypeAdapter(EmailStr).validate_python(value))
        else:
            self.identifier = normalized_phone(value)
            if self.identifier is None:
                raise ValueError('Email hoặc SĐT không được trống.')
        return self


class UserCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=10, max_length=128)
    role_name: RoleName = RoleName.LANDLORD
    status: UserStatus = UserStatus.ACTIVE
    _name = field_validator('full_name')(normalized_name)
    _email = field_validator('email')(ascii_email)
    _phone = field_validator('phone')(normalized_phone)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    password: str | None = Field(default=None, min_length=10, max_length=128)
    role_name: RoleName | None = None
    status: UserStatus | None = None

    @model_validator(mode='after')
    def validate_fields(self):
        if not self.model_fields_set:
            raise ValueError('Chưa có trường cần cập nhật.')
        for field in self.model_fields_set - {'phone'}:
            if getattr(self, field) is None:
                raise ValueError(f'{field} không được null.')
        return self

    @field_validator('full_name')
    @classmethod
    def name(cls, value):
        return normalized_name(value) if value is not None else value

    @field_validator('email')
    @classmethod
    def email_value(cls, value):
        return ascii_email(value) if value is not None else value

    _phone = field_validator('phone')(normalized_phone)


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: UserStatus


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role_name: RoleName


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    role_id: int
    role_name: RoleName
    description: str | None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    role_id: int
    role_name: RoleName
    full_name: str
    email: str
    phone: str | None
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @field_validator('user_id', mode='before')
    @classmethod
    def id_as_string(cls, value):
        return str(value)

    @field_serializer('created_at', 'updated_at')
    def utc_dates(self, value: datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_at: datetime
    role: RoleName
    user: UserOut

    @field_serializer('expires_at')
    def utc_date(self, value: datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')


class UserPage(BaseModel):
    data: list[UserOut]
    page: int
    limit: int
    total: int


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)
    confirm_password: str = Field(min_length=10, max_length=128)

    @model_validator(mode='after')
    def confirm(self):
        if self.new_password != self.confirm_password:
            raise ValueError('Xác nhận mật khẩu mới không khớp.')
        if self.new_password == self.current_password:
            raise ValueError('Mật khẩu mới phải khác mật khẩu hiện tại.')
        return self
