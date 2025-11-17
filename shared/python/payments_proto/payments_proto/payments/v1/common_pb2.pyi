from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class VoidStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VOID_STATUS_UNSPECIFIED: _ClassVar[VoidStatus]
    VOID_STATUS_PENDING: _ClassVar[VoidStatus]
    VOID_STATUS_COMPLETED: _ClassVar[VoidStatus]
    VOID_STATUS_FAILED: _ClassVar[VoidStatus]
    VOID_STATUS_NOT_REQUIRED: _ClassVar[VoidStatus]
VOID_STATUS_UNSPECIFIED: VoidStatus
VOID_STATUS_PENDING: VoidStatus
VOID_STATUS_COMPLETED: VoidStatus
VOID_STATUS_FAILED: VoidStatus
VOID_STATUS_NOT_REQUIRED: VoidStatus

class Money(_message.Message):
    __slots__ = ("amount_cents", "currency")
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    amount_cents: int
    currency: str
    def __init__(self, amount_cents: _Optional[int] = ..., currency: _Optional[str] = ...) -> None: ...

class Timestamp(_message.Message):
    __slots__ = ("seconds", "nanos")
    SECONDS_FIELD_NUMBER: _ClassVar[int]
    NANOS_FIELD_NUMBER: _ClassVar[int]
    seconds: int
    nanos: int
    def __init__(self, seconds: _Optional[int] = ..., nanos: _Optional[int] = ...) -> None: ...

class Address(_message.Message):
    __slots__ = ("line1", "line2", "city", "state", "postal_code", "country")
    LINE1_FIELD_NUMBER: _ClassVar[int]
    LINE2_FIELD_NUMBER: _ClassVar[int]
    CITY_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    POSTAL_CODE_FIELD_NUMBER: _ClassVar[int]
    COUNTRY_FIELD_NUMBER: _ClassVar[int]
    line1: str
    line2: str
    city: str
    state: str
    postal_code: str
    country: str
    def __init__(self, line1: _Optional[str] = ..., line2: _Optional[str] = ..., city: _Optional[str] = ..., state: _Optional[str] = ..., postal_code: _Optional[str] = ..., country: _Optional[str] = ...) -> None: ...

class EventMetadata(_message.Message):
    __slots__ = ("event_id", "correlation_id", "causation_id", "created_at")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    CAUSATION_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    correlation_id: str
    causation_id: str
    created_at: Timestamp
    def __init__(self, event_id: _Optional[str] = ..., correlation_id: _Optional[str] = ..., causation_id: _Optional[str] = ..., created_at: _Optional[_Union[Timestamp, _Mapping]] = ...) -> None: ...

class ErrorDetails(_message.Message):
    __slots__ = ("error_code", "error_message", "is_retryable", "retry_count")
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    IS_RETRYABLE_FIELD_NUMBER: _ClassVar[int]
    RETRY_COUNT_FIELD_NUMBER: _ClassVar[int]
    error_code: str
    error_message: str
    is_retryable: bool
    retry_count: int
    def __init__(self, error_code: _Optional[str] = ..., error_message: _Optional[str] = ..., is_retryable: bool = ..., retry_count: _Optional[int] = ...) -> None: ...
