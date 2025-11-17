from payments.v1 import common_pb2 as _common_pb2
from payments.v1 import authorization_pb2 as _authorization_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AuthRequestCreated(_message.Message):
    __slots__ = ("auth_request_id", "payment_token", "restaurant_id", "amount_cents", "currency", "metadata", "created_at")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_TOKEN_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    payment_token: str
    restaurant_id: str
    amount_cents: int
    currency: str
    metadata: _containers.ScalarMap[str, str]
    created_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., payment_token: _Optional[str] = ..., restaurant_id: _Optional[str] = ..., amount_cents: _Optional[int] = ..., currency: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ..., created_at: _Optional[int] = ...) -> None: ...

class AuthAttemptStarted(_message.Message):
    __slots__ = ("auth_request_id", "worker_id", "restaurant_payment_config_version", "started_at")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    WORKER_ID_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_PAYMENT_CONFIG_VERSION_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    worker_id: str
    restaurant_payment_config_version: str
    started_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., worker_id: _Optional[str] = ..., restaurant_payment_config_version: _Optional[str] = ..., started_at: _Optional[int] = ...) -> None: ...

class AuthResponseReceived(_message.Message):
    __slots__ = ("auth_request_id", "status", "result", "received_at")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    RECEIVED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    status: _authorization_pb2.AuthStatus
    result: _authorization_pb2.AuthorizationResult
    received_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., status: _Optional[_Union[_authorization_pb2.AuthStatus, str]] = ..., result: _Optional[_Union[_authorization_pb2.AuthorizationResult, _Mapping]] = ..., received_at: _Optional[int] = ...) -> None: ...

class AuthAttemptFailed(_message.Message):
    __slots__ = ("auth_request_id", "error_code", "error_message", "is_retryable", "retry_count", "next_retry_at", "failed_at")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    IS_RETRYABLE_FIELD_NUMBER: _ClassVar[int]
    RETRY_COUNT_FIELD_NUMBER: _ClassVar[int]
    NEXT_RETRY_AT_FIELD_NUMBER: _ClassVar[int]
    FAILED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    error_code: str
    error_message: str
    is_retryable: bool
    retry_count: int
    next_retry_at: int
    failed_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., error_code: _Optional[str] = ..., error_message: _Optional[str] = ..., is_retryable: bool = ..., retry_count: _Optional[int] = ..., next_retry_at: _Optional[int] = ..., failed_at: _Optional[int] = ...) -> None: ...

class AuthVoidRequested(_message.Message):
    __slots__ = ("auth_request_id", "reason", "requested_at")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    REQUESTED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    reason: str
    requested_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., reason: _Optional[str] = ..., requested_at: _Optional[int] = ...) -> None: ...

class AuthRequestExpired(_message.Message):
    __slots__ = ("auth_request_id", "expired_at", "reason")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    EXPIRED_AT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    expired_at: int
    reason: str
    def __init__(self, auth_request_id: _Optional[str] = ..., expired_at: _Optional[int] = ..., reason: _Optional[str] = ...) -> None: ...

class AuthRequestQueuedMessage(_message.Message):
    __slots__ = ("auth_request_id", "restaurant_id", "created_at")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    restaurant_id: str
    created_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., restaurant_id: _Optional[str] = ..., created_at: _Optional[int] = ...) -> None: ...

class VoidRequestQueuedMessage(_message.Message):
    __slots__ = ("auth_request_id", "restaurant_id", "reason", "created_at")
    AUTH_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    RESTAURANT_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    auth_request_id: str
    restaurant_id: str
    reason: str
    created_at: int
    def __init__(self, auth_request_id: _Optional[str] = ..., restaurant_id: _Optional[str] = ..., reason: _Optional[str] = ..., created_at: _Optional[int] = ...) -> None: ...
