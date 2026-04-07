from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

from .base import SkillBase
from .registry import PluginRegistry

LOGGER = logging.getLogger(__name__)

# Names of built-in skill modules inside app/skills/
_BUILTIN_SKILL_MODULES = [
    "app.skills.github",
    "app.skills.obsidian",
    "app.skills.browser",
    "app.skills.tts",
]


def load_builtin_skills() -> list[SkillBase]:
    """Import and instantiate all built-in skills."""
    skills: list[SkillBase] = []
    for module_name in _BUILTIN_SKILL_MODULES:
        try:
            module = importlib.import_module(module_name)
            skill_class = getattr(module, "SKILL_CLASS", None)
            if skill_class is None:
                # Try to find the first SkillBase subclass defined in the module
                for attr in vars(module).values():
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, SkillBase)
                        and attr is not SkillBase
                    ):
                        skill_class = attr
                        break
            if skill_class is not None:
                skills.append(skill_class())
            else:
                LOGGER.warning("No SkillBase subclass found in built-in module: %s", module_name)
        except Exception:
            LOGGER.debug("Could not load built-in skill module %s", module_name, exc_info=True)
    return skills


def load_user_skills(skills_dir: Path) -> list[SkillBase]:
    """Load user-installed skills from ``skills_dir``.

    Each subdirectory that contains a ``skill.py`` with a ``SkillBase`` subclass
    (or a ``SKILL_CLASS`` attribute) is loaded.

    Example layout::

        ~/.assistant/skills/
            my_skill/
                skill.py   <- defines MySkill(SkillBase)
    """
    skills: list[SkillBase] = []
    if not skills_dir.exists():
        return skills

    for candidate in sorted(skills_dir.iterdir()):
        if not candidate.is_dir():
            continue
        skill_py = candidate / "skill.py"
        if not skill_py.exists():
            continue
        try:
            module_name = f"_user_skill_{candidate.name}"
            spec = importlib.util.spec_from_file_location(module_name, skill_py)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[attr-defined]

            skill_class = getattr(module, "SKILL_CLASS", None)
            if skill_class is None:
                for attr in vars(module).values():
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, SkillBase)
                        and attr is not SkillBase
                    ):
                        skill_class = attr
                        break

            if skill_class is not None:
                skills.append(skill_class())
                LOGGER.info("Loaded user skill from %s", skill_py)
            else:
                LOGGER.warning("No SkillBase subclass in %s", skill_py)
        except Exception:
            LOGGER.exception("Failed to load user skill from %s", candidate)

    return skills


def build_plugin_registry(
    *,
    user_skills_dir: Path | None = None,
    extra_skills: list[SkillBase] | None = None,
) -> PluginRegistry:
    """Discover and load all skills, return a ready ``PluginRegistry``."""
    skills: list[SkillBase] = []
    skills.extend(load_builtin_skills())
    if user_skills_dir is not None:
        skills.extend(load_user_skills(user_skills_dir))
    if extra_skills:
        skills.extend(extra_skills)
    return PluginRegistry(skills)
