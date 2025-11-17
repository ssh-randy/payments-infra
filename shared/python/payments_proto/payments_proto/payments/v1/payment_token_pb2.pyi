from payments.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EncryptionMetadata(_message.Message):
    __slots__ = ("key_id", "algorithm", "iv")
    KEY_ID_FIELD_NUMBER: _ClassVar[int]
    ALGORITHM_FIELD_NUMBER: _ClassVar[int]
    IV_FIELD_NUMBER: _ClassVar[int]
    key_id: str
    algorithm: str
    iv: str
    def __init__(self, key_id: _Optional[str] = ..., algorithm: _Optional[str] = ..., iv: _Optional[str] = ...) -> None: ...

class CreatePaymentTokenRequest(_message.Message):
    __slots__ = ("restaurant_id", "encrypted_payment_data", "device_token", "idempotency_key", "metadata", "encryption_metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    ENCRYPTED_PAYMENT_DATA_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    ENCRYPTION_METADATA_FIELD_NUMBER: _ClassVar[int]
    restaurant_id: str
    encrypted_payment_data: bytes
    device_token: str
    idempotency_key: str
    metadata: _containers.ScalarMap[str, str]
    encryption_metadata: EncryptionMetadata
    def __init__(self, restaurant_id: _Optional[str] = ..., encrypted_payment_data: _Optional[bytes] = ..., device_token: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ..., encryption_metadata: _Optional[_Union[EncryptionMetadata, _Mapping]] = ...) -> None: ...

class CreatePaymentTokenResponse(_message.Message):
    __slots__ = ("payment_token", "restaurant_id", "expires_at", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    PAYMENT_TOKEN_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    payment_token: str
    restaurant_id: str
    expires_at: int
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, payment_token: _Optional[str] = ..., restaurant_id: _Optional[str] = ..., expires_at: _Optional[int] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class GetPaymentTokenRequest(_message.Message):
    __slots__ = ("payment_token", "restaurant_id")
    PAYMENT_TOKEN_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    payment_token: str
    restaurant_id: str
    def __init__(self, payment_token: _Optional[str] = ..., restaurant_id: _Optional[str] = ...) -> None: ...

class GetPaymentTokenResponse(_message.Message):
    __slots__ = ("payment_token", "restaurant_id", "created_at", "expires_at", "is_expired", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    PAYMENT_TOKEN_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    IS_EXPIRED_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    payment_token: str
    restaurant_id: str
    created_at: int
    expires_at: int
    is_expired: bool
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, payment_token: _Optional[str] = ..., restaurant_id: _Optional[str] = ..., created_at: _Optional[int] = ..., expires_at: _Optional[int] = ..., is_expired: bool = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class DecryptPaymentTokenRequest(_message.Message):
    __slots__ = ("payment_token", "restaurant_id", "requesting_service")
    PAYMENT_TOKEN_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    REQUESTING_SERVICE_FIELD_NUMBER: _ClassVar[int]
    payment_token: str
    restaurant_id: str
    requesting_service: str
    def __init__(self, payment_token: _Optional[str] = ..., restaurant_id: _Optional[str] = ..., requesting_service: _Optional[str] = ...) -> None: ...

class DecryptPaymentTokenResponse(_message.Message):
    __slots__ = ("payment_data", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    PAYMENT_DATA_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    payment_data: PaymentData
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, payment_data: _Optional[_Union[PaymentData, _Mapping]] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class PaymentData(_message.Message):
    __slots__ = ("card_number", "exp_month", "exp_year", "cvv", "cardholder_name", "billing_address")
    CARD_NUMBER_FIELD_NUMBER: _ClassVar[int]
    EXP_MONTH_FIELD_NUMBER: _ClassVar[int]
    EXP_YEAR_FIELD_NUMBER: _ClassVar[int]
    CVV_FIELD_NUMBER: _ClassVar[int]
    CARDHOLDER_NAME_FIELD_NUMBER: _ClassVar[int]
    BILLING_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    card_number: str
    exp_month: str
    exp_year: str
    cvv: str
    cardholder_name: str
    billing_address: _common_pb2.Address
    def __init__(self, card_number: _Optional[str] = ..., exp_month: _Optional[str] = ..., exp_year: _Optional[str] = ..., cvv: _Optional[str] = ..., cardholder_name: _Optional[str] = ..., billing_address: _Optional[_Union[_common_pb2.Address, _Mapping]] = ...) -> None: ...
