"""Create an isolated shared/user data tree; never touch installed Rime paths."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
runtime = HERE / "runtime"
shared = runtime / "shared"
user = runtime / "user"
shared.mkdir(parents=True, exist_ok=True)
user.mkdir(parents=True, exist_ok=True)
shutil.copytree(ROOT / ".cache/weasel-0.17.4/data", shared, dirs_exist_ok=True)
shutil.copytree(HERE / "fixtures", user, dirs_exist_ok=True)
shutil.copy2(ROOT / "src/study/lua/study_core.lua", user / "lua/study_core.lua")
schema = (HERE / "fixtures/study.schema.yaml").read_text(encoding="utf-8")
baseline = schema.replace("schema_id: study", "schema_id: study_base").replace(
    "    - lua_processor@study_keys\n", ""
).replace("    - lua_filter@study_filter\n", "")
(user / "study_base.schema.yaml").write_text(baseline, encoding="utf-8")
partial = schema.replace("schema_id: study", "schema_id: study_partial").replace(
    "  enable_user_dict: false", "  enable_user_dict: false\n  enable_sentence: false"
)
(user / "study_partial.schema.yaml").write_text(partial, encoding="utf-8")
(user / "default.custom.yaml").write_text(
    "patch:\n  schema_list:\n    - {schema: study}\n    - {schema: study_base}\n    - {schema: study_partial}\n",
    encoding="utf-8",
)
print(runtime)
