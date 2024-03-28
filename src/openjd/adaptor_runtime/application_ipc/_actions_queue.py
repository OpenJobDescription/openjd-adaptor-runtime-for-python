# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING
from typing import Deque
from typing import Optional

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from openjd.adaptor_runtime_client import Action


class ActionsQueue:
    """This class will manage the Queue of Actions. This class will be responsible for
    enqueueing, or dequeueing Actions, and converting actions to and from json strings."""

    _actions_queue: Deque[Action]

    def __init__(self) -> None:
        self._actions_queue = deque()

    def enqueue_action(self, a: Action, front: bool = False) -> None:
        """This function will enqueue the action to the end of the queue.

        Args:
            a (Action): The action to be enqueued.
            front (bool, optional): Whether we want to append to the front of the queue.
                                    Defaults to False.
        """
        if front:
            self._actions_queue.appendleft(a)
        else:
            self._actions_queue.append(a)

    def dequeue_action(self) -> Optional[Action]:
        if len(self) > 0:
            return self._actions_queue.popleft()
        else:
            return None

    def __bool__(self) -> bool:
        return bool(self._actions_queue)

    def __len__(self) -> int:
        return len(self._actions_queue)
