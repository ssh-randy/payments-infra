from payments.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AuthStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUTH_STATUS_UNSPECIFIED: _ClassVar[AuthStatus]
    AUTH_STATUS_PENDING: _ClassVar[AuthStatus]
    AUTH_STATUS_PROCESSING: _ClassVar[AuthStatus]
    AUTH_STATUS_AUTHORIZED: _ClassVar[AuthStatus]
    AUTH_STATUS_DENIED: _ClassVar[AuthStatus]
    AUTH_STATUS_FAILED: _ClassVar[AuthStatus]
    AUTH_STATUS_VOIDED: _ClassVar[AuthStatus]
    AUTH_STATUS_EXPIRED: _ClassVar[AuthStatus]
AUTH_STATUS_UNSPECIFIED: AuthStatus
AUTH_STATUS_PENDING: AuthStatus
AUTH_STATUS_PROCESSING: AuthStatus
AUTH_STATUS_AUTHORIZED: AuthStatus
AUTH_STATUS_DENIED: AuthStatus
AUTH_STATUS_FAILED: AuthStatus
AUTH_STATUS_VOIDED: AuthStatus
AUTH_STATUS_EXPIRED: AuthStatus

class AuthorizeRequest(_message.Message):
    __slots__ = ("payment_token", "restaurant_id", "amount_cents", "currency", "idempotency_key", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    PAYMENT_TOKEN_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    payment_token: str
    restaurant_id: str
    amount_cents: int
    currency: str
    idempotency_key: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, payment_token: _Optional[str] = ..., restaurant_id: _Optional[str] = ..., amount_cents: _Optional[int] = ..., currency: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class AuthorizeResponse(_message.Message):
    __slots__ = ("auth_request_id", "status", "result", "status_url")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    STATUS_URL_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    status: AuthStatus
    result: AuthorizationResult
    status_url: str
    def __init__(self, auth_request_id: _Optional[str] = ..., status: _Optional[_Union[AuthStatus, str]] = ..., result: _Optional[_Union[AuthorizationResult, _Mapping]] = ..., status_url: _Optional[str] = ...) -> None: ...

class AuthorizationResult(_message.Message):
    __slots__ = ("processor_auth_id", "processor_name", "authorized_amount_cents", "currency", "authorization_code", "authorized_at", "denial_code", "denial_reason", "processor_metadata")
    class ProcessorMetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    PROCESSOR_AUTH_ID_FIELD_NUMBER: _ClassVar[int]
    PROCESSOR_NAME_FIELD_NUMBER: _ClassVar[int]
    AUTHORIZED_AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    AUTHORIZATION_CODE_FIELD_NUMBER: _ClassVar[int]
    AUTHORIZED_AT_FIELD_NUMBER: _ClassVar[int]
    DENIAL_CODE_FIELD_NUMBER: _ClassVar[int]
    DENIAL_REASON_FIELD_NUMBER: _ClassVar[int]
    PROCESSOR_METADATA_FIELD_NUMBER: _ClassVar[int]
    processor_auth_id: str
    processor_name: str
    authorized_amount_cents: int
    currency: str
    authorization_code: str
    authorized_at: int
    denial_code: str
    denial_reason: str
    processor_metadata: _containers.ScalarMap[str, str]
    def __init__(self, processor_auth_id: _Optional[str] = ..., processor_name: _Optional[str] = ..., authorized_amount_cents: _Optional[int] = ..., currency: _Optional[str] = ..., authorization_code: _Optional[str] = ..., authorized_at: _Optional[int] = ..., denial_code: _Optional[str] = ..., denial_reason: _Optional[str] = ..., processor_metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class GetAuthStatusRequest(_message.Message):
    __slots__ = ("auth_request_id", "restaurant_id")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    restaurant_id: str
    def __init__(self, auth_request_id: _Optional[str] = ..., restaurant_id: _Optional[str] = ...) -> None: ...

class GetAuthStatusResponse(_message.Message):
    __slots__ = ("auth_request_id", "status", "result", "created_at", "updated_at")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    status: AuthStatus
    result: AuthorizationResult
    created_at: int
    updated_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., status: _Optional[_Union[AuthStatus, str]] = ..., result: _Optional[_Union[AuthorizationResult, _Mapping]] = ..., created_at: _Optional[int] = ..., updated_at: _Optional[int] = ...) -> None: ...

class VoidAuthRequest(_message.Message):
    __slots__ = ("auth_request_id", "restaurant_id", "reason", "idempotency_key")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    restaurant_id: str
    reason: str
    idempotency_key: str
    def __init__(self, auth_request_id: _Optional[str] = ..., restaurant_id: _Optional[str] = ..., reason: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class VoidAuthResponse(_message.Message):
    __slots__ = ("auth_request_id", "status", "voided_at")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    VOIDED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    status: _common_pb2.VoidStatus
    voided_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., status: _Optional[_Union[_common_pb2.VoidStatus, str]] = ..., voided_at: _Optional[int] = ...) -> None: ...
