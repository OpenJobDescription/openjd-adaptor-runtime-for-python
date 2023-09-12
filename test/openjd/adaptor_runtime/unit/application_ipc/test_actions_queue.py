# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from collections import deque as _deque

from openjd.adaptor_runtime_client import Action as _Action

from openjd.adaptor_runtime.application_ipc import ActionsQueue as _ActionsQueue


class TestActionsQueue:
    def test_actions_queue(self) -> None:
        """Testing that we can enqueue correctly."""
        aq = _ActionsQueue()

        # Confirming the actions queue has been initialized.
        assert aq._actions_queue == _deque()

        # Testing enqueue_action works as expected.
        aq.enqueue_action(_Action("a1"))
        aq.enqueue_action(_Action("a2"))
        aq.enqueue_action(_Action("a3"))

        # Asserting actions were enqueued in order.
        assert len(aq) == 3
        assert aq.dequeue_action() == _Action("a1")
        assert aq.dequeue_action() == _Action("a2")
        assert aq.dequeue_action() == _Action("a3")
        assert aq.dequeue_action() is None

    def test_actions_queue_append_start(self) -> None:
        aq = _ActionsQueue()

        # Testing enqueue_action works as expected.
        aq.enqueue_action(_Action("a1"))
        aq.enqueue_action(_Action("a4"), front=True)

        # Asserting actions were enqueued in order.
        assert len(aq) == 2
        assert aq.dequeue_action() == _Action("a4")
        assert aq.dequeue_action() == _Action("a1")
        assert aq.dequeue_action() is None

    def test_len(self) -> None:
        """Testing that our overriden __len__ works as expected."""
        aq = _ActionsQueue()

        # Starting off with an empty queue.
        assert len(aq) == 0

        # Adding 1 item to the queue.
        aq.enqueue_action(_Action("a1"))
        assert len(aq) == 1

        # Adding a second item to the queue.
        aq.enqueue_action(_Action("a2"))
        assert len(aq) == 2

        # Removing the first items from the queue.
        aq.dequeue_action()
        assert len(aq) == 1

        # Removing the last from the queue.
        aq.dequeue_action()
        assert len(aq) == 0

    def test_bool(self) -> None:
        """Testing that our overriden __bool__ works as expected."""
        aq = _ActionsQueue()

        # Starting off with an empty queue.
        assert not bool(aq)

        # Adding 1 item to the queue.
        aq.enqueue_action(_Action("a1"))
        assert bool(aq)

        # Adding a second item to the queue.
        aq.enqueue_action(_Action("a2"))
        assert bool(aq)

        # Removing the first items from the queue.
        aq.dequeue_action()
        assert bool(aq)

        # Removing the last from the queue.
        aq.dequeue_action()
        assert not bool(aq)
