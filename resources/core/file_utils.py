import asyncio
import json
import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


class FileManager:
    @staticmethod
    def ensure_directory(path: Path) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def write_text(path: Path, text: str) -> None:
        FileManager.ensure_directory(path)

        temp_path = path.with_name(f"{path.name}.tmp")

        try:
            with temp_path.open("w", encoding="utf-8") as file:
                file.write(text)
                file.flush()
                os.fsync(file.fileno())

            os.chmod(temp_path, 0o660)
            os.replace(temp_path, path)
            # NOTE: This gives all store files a permission of 660.
            # Bot written files must be accessible by the bot
            # obviously, but also the group,
            # So that they can be accessed by my user
            # (the only other in the group) for bug investigation.
            # SystemD will specify the intended permissions group
            # in the unit file.

            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)

            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def read_text(path: Path) -> str:
        return path.read_text(
            encoding="utf-8",
        )

    @staticmethod
    def read_json(path: Path) -> dict[str, Any]:

        try:
            text = FileManager.read_text(path)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Missing file {path}: {e}")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in store file {path}: {e}")

        if not isinstance(data, dict):
            raise ValueError(
                f"Expected a JSON object at the root of store file {
                    path
                }, got {type(data).__name__}"
            )

        return data

    @staticmethod
    def write_json(path: Path, data) -> None:

        FileManager.write_text(
            path,
            json.dumps(
                data,
                indent=4,
                ensure_ascii=False,
            ),
        )


class JsonStore:
    FLUSH_DELAY = 0.5
    MAX_FLUSH_DEFERRALS = 4

    def __init__(self, path: Path, logger: logging.Logger) -> None:
        self.path = path
        self.logger = logger

        self._lock = asyncio.Lock()

        self._data = FileManager.read_json(path)

        self._dirty = False

        self._flush_task = None

        self._flush_deferrals = 0

        self._closing = False

    def _close_check(self) -> None:
        if self._closing:
            raise RuntimeError("Store closing; operation ignored.")

    def _resolve_path(
        self, data: dict, path: str, create: bool = False
    ) -> tuple[dict, str]:

        keys = [key for key in path.strip("#/").split("/") if key]

        if not keys:
            raise ValueError("Path cannot be empty")

        current = data

        for key in keys[:-1]:
            if key not in current:
                if create:
                    current[key] = {}
                else:
                    raise KeyError(key)

            current = current[key]

            if not isinstance(current, dict):
                raise KeyError(key)

        return current, keys[-1]

    # DICTIONARY OPERATIONS

    async def read(self, path: str) -> Any:
        self._close_check()

        async with self._lock:
            self._close_check()

            parent, key = self._resolve_path(self._data, path)

            return deepcopy(parent[key])

    # Returns key value if it exists. If not, raises
    # KeyError

    async def exists(self, path: str) -> bool:
        self._close_check()

        async with self._lock:
            self._close_check()
            try:
                parent, key = self._resolve_path(self._data, path)
                return key in parent
            except KeyError:
                return False

    # Returns false if key does not exist
    # or cannot be found. Returns true if it does.

    async def get(self, path: str, default: Any = None) -> Any:
        self._close_check()

        async with self._lock:
            self._close_check()
            try:
                parent, key = self._resolve_path(self._data, path)
                return deepcopy(parent[key])
            except KeyError:
                return deepcopy(default)

    # Returns the specified default if key does not exist
    # or cannot be found. Returns found value if it does.

    async def setdefault(self, path: str, default: Any) -> Any:
        self._close_check()

        async with self._lock:
            self._close_check()

            parent, key = self._resolve_path(self._data, path, create=True)

            if key not in parent:
                parent[key] = deepcopy(default)

                self._dirty = True
                self._schedule_flush()

                return None

            return deepcopy(parent[key])

    # If key does not exist, write specified default to it and return None.
    # If it does, leave it alone and return the found value.

    async def write(self, path: str, value: Any) -> None:
        self._close_check()

        async with self._lock:
            self._close_check()

            parent, key = self._resolve_path(
                self._data,
                path,
                create=True,
            )

            parent[key] = deepcopy(value)

            self._dirty = True
            self._schedule_flush()

    # Write specified value to key whether or not it exists.

    async def update(self, path: str, values: dict) -> None:
        self._close_check()

        async with self._lock:
            self._close_check()

            parent, key = self._resolve_path(
                self._data,
                path,
                create=True,
            )

            if key not in parent:
                parent[key] = {}

            if not isinstance(parent[key], dict):
                raise TypeError(f"Expected a dictionary at {path}.")

            parent[key].update(deepcopy(dict(values)))

            self._dirty = True
            self._schedule_flush()

    # Updates target dictionary with supplied dictionary.

    async def delete(self, path: str) -> bool:
        self._close_check()

        async with self._lock:
            self._close_check()

            try:
                parent, key = self._resolve_path(self._data, path)
            except KeyError:
                return False

            if key not in parent:
                return False

            del parent[key]

            self._dirty = True
            self._schedule_flush()

            return True

    # Returns false if key does not exist or cannot be found.
    # Returns true if it does, and the key is deleted.

    # LIST OPERATIONS

    async def list_pop(self, path: str, index: int = 0) -> Any | None:
        self._close_check()

        async with self._lock:
            self._close_check()

            try:
                parent, key = self._resolve_path(self._data, path)

                bucket = parent[key]
            except KeyError:
                return None

            if not isinstance(bucket, list):
                raise TypeError(f"Expected a list at {path}")

            if not bucket:
                return None

            if not -len(bucket) <= index < len(bucket):
                return None

            value = bucket.pop(index)

            self._dirty = True
            self._schedule_flush()

            return deepcopy(value)

    # Returns none if list element and its parent list do not exist
    # or cannot be found. Returns the list element if they do.

    async def list_append(self, path: str, value: Any) -> None:
        self._close_check()

        async with self._lock:
            self._close_check()

            parent, key = self._resolve_path(self._data, path, create=True)

            if key not in parent:
                parent[key] = []

            if not isinstance(parent[key], list):
                raise TypeError(f"Expected a list at {path}")

            parent[key].append(deepcopy(value))

            self._dirty = True
            self._schedule_flush()

    async def list_extend(self, path: str, values: list[Any]) -> None:
        self._close_check()

        async with self._lock:
            self._close_check()

            parent, key = self._resolve_path(self._data, path, create=True)

            if key not in parent:
                parent[key] = []

            if not isinstance(parent[key], list):
                raise TypeError(f"Expected a list at {path}")

            parent[key].extend(deepcopy(values))

            self._dirty = True
            self._schedule_flush()

    async def list_clear(self, path: str) -> bool:
        self._close_check()

        async with self._lock:
            self._close_check()

            try:
                parent, key = self._resolve_path(self._data, path)

                bucket = parent[key]
            except KeyError:
                return False

            if not isinstance(bucket, list):
                raise TypeError(f"Expected a list at {path}.")

            if not bucket:
                return False

            bucket.clear()

            self._dirty = True
            self._schedule_flush()

            return True

    # Returns false if list do not exist or cannot be found.
    # Returns true if it does, and the list is cleared.

    async def list_remove(self, path: str, value: Any) -> bool:
        self._close_check()

        async with self._lock:
            self._close_check()

            try:
                parent, key = self._resolve_path(self._data, path)

                bucket = parent[key]
            except KeyError:
                return False

            if not isinstance(bucket, list):
                raise TypeError(f"Expected a list at {path}.")

            try:
                bucket.remove(value)
            except ValueError:
                return False

            self._dirty = True
            self._schedule_flush()

            return True

    # Returns false if list element and its parent list do not exist
    # or cannot be found. Returns true if they do and list element is removed.

    async def list_contains(self, path: str, value: Any) -> bool:
        self._close_check()

        async with self._lock:
            self._close_check()

            try:
                parent, key = self._resolve_path(self._data, path)

                bucket = parent[key]
            except KeyError:
                return False

            if not isinstance(bucket, list):
                raise TypeError(f"Expected a list at {path}.")

            return value in bucket

    # Returns false if list element and its parent list do not exist
    # or cannot be found. Returns true if they do, and list element is in list.

    async def list_length(self, path: str) -> int:
        self._close_check()

        async with self._lock:
            self._close_check()

            try:
                parent, key = self._resolve_path(self._data, path)

                bucket = parent[key]
            except KeyError:
                return 0

            if not isinstance(bucket, list):
                raise TypeError(f"Expected a list at {path}.")

            return len(bucket)

    # Returns the length of a store list (0 if the list does not exist or
    # cannot be found.)

    async def list_element_index(self, path: str, value: Any) -> int | None:
        self._close_check()

        async with self._lock:
            self._close_check()

            try:
                parent, key = self._resolve_path(self._data, path)

                bucket = parent[key]
            except KeyError:
                return None

            if not isinstance(bucket, list):
                raise TypeError(f"Expected a list at {path}.")

            for index, item in enumerate(bucket):
                if item == value:
                    return index

            return None

    # Returns none if the specified element or its parent list do not exist
    # or cannot be found. Returns index of element in parent list if it does.

    def _schedule_flush(self) -> None:
        async def _delayed_flush(expedite: bool) -> None:
            if not expedite:
                await asyncio.sleep(self.FLUSH_DELAY)
            try:
                await self.flush()
            except Exception:
                self.logger.exception(
                    f"Delayed flush failed for JSON store {
                        self.path
                    }. Changes remain dirty and will be retried on next write/close."
                )

                if self._flush_task is asyncio.current_task():
                    self._flush_task = None

        if self._flush_task is not None:
            if self._flush_task.done():
                self._flush_task = None

            elif self._flush_deferrals >= self.MAX_FLUSH_DEFERRALS:
                return

            else:
                self._flush_task.cancel()
                self._flush_deferrals += 1

        self._flush_task = asyncio.create_task(
            _delayed_flush(
                expedite=(self._flush_deferrals >= self.MAX_FLUSH_DEFERRALS)
            )
        )

    async def wait_for_flush(self) -> None:
        task = self._flush_task

        while task == self._flush_task is not None:
            try:
                await asyncio.shield(task)

            except asyncio.CancelledError:
                current = asyncio.current_task()

                if (
                    task.cancelled()
                    and current is not None
                    and current.cancelling() == 0
                ):
                    continue

                raise

    async def flush(self) -> None:
        async with self._lock:
            if not self._dirty:
                if self._flush_task is asyncio.current_task():
                    self._flush_task = None
                return

            await asyncio.to_thread(
                FileManager.write_json,
                self.path,
                self._data,
            )

            self._dirty = False
            self._flush_deferrals = 0

            if self._flush_task is asyncio.current_task():
                self._flush_task = None

    # NOTE: The way this is done *should* prevent task cancellation race
    # conditions as flush() holds the lock for the entire duration of the write
    # and only releases it once it's done. write() therefore cannot proceed
    # to scheduling a new task (and potentially cancelling the ongoing one)
    # if flush() has already started. This depends on _schedule_flush() only
    # ever being called by methods that hold _lock, which is the case now, but
    # needs to stay that way.

    async def close(self) -> None:
        self._closing = True

        try:
            if self._flush_task is not None:
                await self._flush_task
        finally:
            await self.flush()
