# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import dataclasses as dataclasses
import json as json
from enum import Enum as Enum
from enum import EnumMeta
from typing import Any, ClassVar, Dict, Type, TypeVar, cast, Generic

from ..adaptors import AdaptorState

_T = TypeVar("_T")


@dataclasses.dataclass
class ConnectionSettings:
    socket: str


class AdaptorStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"


@dataclasses.dataclass
class BufferedOutput:
    EMPTY: ClassVar[str] = "EMPTY"

    id: str
    output: str


@dataclasses.dataclass
class HeartbeatResponse:
    state: AdaptorState
    status: AdaptorStatus
    output: BufferedOutput
    failed: bool = False


class DataclassJSONEncoder(json.JSONEncoder):  # pragma: no cover
    def default(self, o: Any) -> Dict:
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        else:
            return super().default(o)


class DataclassMapper(Generic[_T]):
    """
    Class that maps a dictionary to a dataclass.

    The main reason this exists is to support nested dataclasses. Dataclasses are represented as
    dict when serialized, and when they are nested we get a nested dictionary structure. For a
    simple dataclass, we can easily go from a dict to a dataclass instance by expanding the
    dictionary into keyword arguments for the dataclass' __init__ function. e.g.

    ```
    @dataclass
    class FullName:
        first: str
        last: str

    my_dict = {"first": "John", "last": "Doe"}
    name_instance = FullName(**my_dict)
    ```

    However, in a nested structure, this will not work because the parent dataclass' __init__
    function expects instance(s) of the nested dataclass(es), not a dictionary. For example,
    building on the previous code snippet:

    ```
    @dataclass
    class Person:
        age: int
        name: FullName

    my_dict = {
        "age": 30,
        "name": {
            "first": "John",
            "last": "Doe",
        },
    }
    person_instance = Person(**my_dict)
    ```

    The above code is not valid because Person.__init__ expects an instance of FullName for the
    "name" argument, not a dict with the keyword args. This class handles this case by checking
    each field to see if it is a dataclass and instantiating that dataclass for you.
    """

    def __init__(self, cls: Type[_T]) -> None:
        self._cls = cls
        super().__init__()

    def map(self, o: Dict) -> _T:
        args: Dict = {}
        for field in dataclasses.fields(self._cls):  # type: ignore
            if field.name not in o:
                raise ValueError(f"Dataclass field {field.name} not found in dict {o}")

            value = o[field.name]
            if dataclasses.is_dataclass(field.type):
                # The init function expects a type, so any dataclasses in cls
                # will be a type.
                value = DataclassMapper(cast(type, field.type)).map(value)
            elif isinstance(field.type, EnumMeta):
                value = field.type(value)

            args[field.name] = value

        return self._cls(**args)
