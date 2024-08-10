"""
Hence
"""

from __future__ import annotations
from collections import UserDict
from contextvars import ContextVar
from functools import wraps, cached_property
from itertools import zip_longest
import logging
import sys
from types import FunctionType
from typing import Any, NamedTuple, Optional, Protocol, Union

from immutabledict import immutabledict
from paradag import DAG, SequentialProcessor, MultiThreadProcessor, dag_run


CTX_NAME = "hence_context"
CTX_FN_BASE = "func"
CTX_TI_BASE = "title"
CTX_GR_BASE = "group"


class TitleConfig(NamedTuple):
    """TitleConfig"""

    task_key: str
    title: str


class GroupConfig(NamedTuple):
    """GroupConfig"""

    title: str
    function: FunctionType


class TaskConfig:
    """TaskConfig"""

    def __init__(
        self, fn: FunctionType, params: dict, rid: str = "", sid: str = ""
    ) -> None:
        """constructor"""

        if not sid:
            raise ValueError("Sequence id empty.")

        _title = hence_config.context_get(CTX_TI_BASE, fn.__name__)

        self.function: FunctionType = fn
        self.parameters: immutabledict = immutabledict(params)
        self.run_id: str = rid
        self.seq_id: str = sid
        self.title: str = _title if _title else fn.__name__
        self.result: Any = None

    @cached_property
    def task_key(self) -> str:
        """Make a context key for functions"""

        if not self.function:
            raise ValueError("function is empty.")

        task_key_ = f"{self.function.__name__}.{self.seq_id}"

        if self.run_id:
            task_key_ += "." + self.run_id

        return task_key_

    def asdict(self) -> dict:
        """asdict"""

        result = self.__dict__
        if "parameters" in result:
            result["parameters"] = dict(result["parameters"])

        return result

    def __repr__(self) -> str:
        """__repr__"""

        return str(self.asdict())


class RunLevelContext(UserDict):
    """Context data for Group and bloc of Task"""

    def __setitem__(self, key: str, item: TaskConfig) -> None:
        """Add a TaskConfig to data"""

        if not isinstance(item, TaskConfig):
            raise TypeError("A TaskConfig for given.")

        if key in self.data:
            raise ValueError("TaskConfig exists.")

        super().__setitem__(key, item)

    def __getitem__(self, key: str) -> Optional[TaskConfig]:
        """Get a TaskConfig"""

        return self.data[key] if key in self.data else None

    def step(self, step: int) -> Optional[TaskConfig]:
        """Get specific step"""

        for key_ in self.data.keys():
            if f"{step}." in key_:
                return self.data[key_]

        return None


class HenceLogger:
    """HenceLogger"""

    DEBUG = "debug"
    ERROR = "error"

    def __init__(self):
        """Loads or reloads logger"""

        self.logger = logging.getLogger("hence")
        self.enable_logging = False

        self._setup_logger_()

    def _setup_logger_(self):
        """setup logger"""

        stderr_log_formatter = logging.Formatter(
            "%(name)s :: %(levelname)s :: "
            + "(P)%(process)d/(Th)%(thread)d :: "
            + "%(message)s"
        )

        stdout_log_handler = logging.StreamHandler(stream=sys.stderr)
        stdout_log_handler.setLevel(logging.NOTSET)
        stdout_log_handler.setFormatter(stderr_log_formatter)

        self.logger.addHandler(stdout_log_handler)
        self.logger.setLevel(logging.DEBUG)

    def log(self, level: str, message: str, *args) -> None:
        """Final logging function"""

        if not self.enable_logging:
            return

        if level not in (self.DEBUG, self.ERROR):
            raise SystemError("Invalid log type.")

        self.logger.log(
            logging.DEBUG if level == _logger.DEBUG else logging.ERROR, message, *args
        )


class HenceContext:
    """Hence configuration class"""

    def __init__(self) -> None:
        """Constructor"""

        self.context: ContextVar[dict] = None

        self._setup_context()

    def _setup_context(self) -> None:
        """Setup contextvar"""
        del self.context

        self.context: ContextVar[dict] = ContextVar(
            CTX_NAME,
            default={
                CTX_FN_BASE: {},
                CTX_GR_BASE: {},
                CTX_TI_BASE: {},
            },
        )

    def context_add(self, obj: TaskConfig | GroupConfig | TitleConfig) -> None:
        """Add to context"""

        if not isinstance(obj, (TaskConfig, GroupConfig, TitleConfig)):
            raise TypeError("context_add :: unsupported type")

        if isinstance(obj, TaskConfig):
            context_val = self.context.get()
            context_val[CTX_FN_BASE][obj.task_key] = obj

        elif isinstance(obj, TitleConfig):
            context_val = self.context.get()
            context_val[CTX_TI_BASE][obj.task_key] = obj.title

        elif isinstance(obj, GroupConfig):
            context_val = self.context.get()

            if obj.title not in context_val[CTX_GR_BASE]:
                context_val[CTX_GR_BASE][obj.title] = [obj.function]
            else:
                context_val[CTX_GR_BASE][obj.title].append(obj.function)

        _logger.log(_logger.DEBUG, "Context:: %s.", self.context)

    def context_get(self, key: str, obj_key: str = "") -> Any:
        """Get from context"""

        context_val = self.context.get()

        if key not in context_val:
            _logger.log(_logger.ERROR, "Object with key: `%s` not found.", key)
            raise KeyError(f"Object with key: `{key}` not found.")

        if obj_key and obj_key not in context_val[key]:
            _logger.log(_logger.ERROR, "Object with key: `%s` not found.", obj_key)
            raise KeyError(f"Object with key: `{obj_key}` not found.")

        ret_value = context_val[key][obj_key] if obj_key else context_val[key]

        _logger.log(
            _logger.DEBUG, " :: context_get ::`%s` for %s.%s.", ret_value, key, obj_key
        )

        return ret_value

    def task(self, obj_key: str) -> TaskConfig:
        """Get a task by key"""

        return self.context_get(CTX_FN_BASE, obj_key)


_logger = HenceLogger()

hence_config = HenceContext()


def group(group_id: str) -> Any:
    """Group"""

    group_lst = hence_config.context_get(CTX_GR_BASE)

    if group_id in group_lst:
        raise ValueError(f"`{group_id}` exists already.")

    def _internal(fn: FunctionType):
        """Internal handler"""

        hence_config.context_add(GroupConfig(title=group_id, function=fn))

    return _internal


def task(title: str = None) -> Any:
    """Task"""

    def _internal(function: FunctionType):
        """Internal handler"""

        t_title = title if title else function.__name__

        # save function title to context
        _logger.log(_logger.DEBUG, "title `%s` registered.", t_title)

        t_conf = TitleConfig(function.__name__, t_title)
        hence_config.context_add(t_conf)

        if "kwargs" not in function.__code__.co_varnames:
            _logger.log(
                _logger.ERROR, "Missing `**kwargs` in %s args.", function.__name__
            )
            raise TypeError(f"Missing `**kwargs` in {function.__name__} args.")

        @wraps(function)
        def _decorator(**kwargs: dict) -> Any:
            """decorator"""

            _logger.log(
                _logger.DEBUG, "`%s` called with %s.", function.__name__, kwargs
            )
            return function(**kwargs)

        return _decorator

    return _internal


def run_tasks(fn_config_list: list[tuple], run_id: str = "") -> list[str]:
    """Run @task"""

    fn_list = []

    for index, fn_config_tpl in enumerate(fn_config_list):
        _logger.log(_logger.DEBUG, "`run_tasks` :: %s", fn_config_tpl)

        if len(fn_config_tpl) > 2:

            raise ValueError(
                f"Only function and parameters are allowed in `{run_tasks.__name__}`"
            )

        fn_config = TaskConfig(sid=str(index), rid=run_id, *fn_config_tpl)
        hence_config.context_add(fn_config)

        fn_list.append(fn_config.task_key)

    if not fn_list:
        _logger.log(_logger.ERROR, "`fn_list` does not contain any `@task`.")
        raise TypeError("`fn_list` does not contain any `@task`.")

    _dag = setup_dag(fn_list)
    return execute_dag(_dag, SequentialProcessor(), FunctionTypeExecutor())


def run_group(group_id: str, task_params: list[dict]) -> Any:
    """Run groups"""

    groups = hence_config.context_get(CTX_GR_BASE)

    if group_id not in groups:
        raise RuntimeError(f"group `{group_id}` is not found.")

    group_params = list(
        zip_longest(
            groups[group_id],
            task_params,
            fillvalue={},
        )
    )

    return run_tasks(group_params, group_id)


def setup_dag(vertices: list) -> DAG:
    """Setup DAG"""

    _dag = DAG()

    _dag.add_vertex(*vertices)

    for index in range(1, len(vertices)):
        _dag.add_edge(vertices[index - 1], vertices[index])

    return _dag


def execute_dag(
    dag: DAG,
    ps: Union[SequentialProcessor, MultiThreadProcessor],
    ex: ExecutorContract,
) -> list:
    """Execute the dag"""

    if not isinstance(dag, DAG):
        raise TypeError(f"Not a DAG. type: {type(dag)}")

    return dag_run(dag, processor=ps, executor=ex)


class ExecutorContract(Protocol):
    """Interface for Executor"""

    def param(self, vertex) -> Any:
        """Have param"""

    def execute(self, __work) -> Any:
        """Can execute"""

    def report_finish(self, vertices_result):
        """Reports final steps"""


class FunctionTypeExecutor:
    """Linear executor"""

    def __init__(self) -> None:
        """init FunctionTypeExecutor"""

        self._results = {}

    def param(self, vertex: Any) -> Any:
        """Selecting parameters"""

        return vertex

    def execute(self, task_key: str) -> Any:
        """Execute"""

        fn_cfg: TaskConfig = hence_config.context_get(CTX_FN_BASE, task_key)

        t_title: str = fn_cfg.title

        # replace supported variables in title
        if "{" in t_title and "}" in t_title:

            try:
                t_title = t_title.format(
                    fn_key=fn_cfg.task_key,
                    fn_name=fn_cfg.function.__name__,
                    fn_run_id=fn_cfg.run_id,
                    fn_seq_id=fn_cfg.seq_id,
                )
            except KeyError as e:
                _logger.log(_logger.ERROR, "`%s` not found in task.title.", str(e))
                raise e

            fn_cfg.title = t_title
            hence_config.context_add(fn_cfg)

        _logger.log(_logger.DEBUG, "`%s::%s` is executing.", t_title, task_key)

        return fn_cfg.function(**fn_cfg.parameters)

    def report_finish(self, vertices_result: list):
        """After execution finished"""

        fn_key, fn_result = vertices_result[0]

        fn_obj: TaskConfig = hence_config.context_get(CTX_FN_BASE, fn_key)
        fn_obj.result = fn_result

        hence_config.context_add(fn_obj)
