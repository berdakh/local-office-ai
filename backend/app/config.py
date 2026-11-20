"""Application settings. Everything is overridable with LOA_* environment variables."""

from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote, urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOA_", env_file=".env", extra="ignore")

    data_dir: Path = Path.home() / "LocalOfficeAI"
    pack: str = "church"
    packs_dir: Path = REPO_ROOT / "packs"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3:8b"
    chat_context: int = Field(default=8192, ge=2048)
    embed_model: str = "nomic-embed-text"
    whisper_model: str = "small"
    whisper_model_dir: Path | None = None

    pin: str = ""

    chunk_size: int = 800
    chunk_overlap: int = 120

    @field_validator("ollama_url")
    @classmethod
    def validate_local_ollama_url(cls, value: str) -> str:
        url = urlsplit(value)
        host = url.hostname or ""
        try:
            is_loopback = ip_address(host).is_loopback
        except ValueError:
            is_loopback = host == "localhost"
        if (
            not is_loopback
            or url.scheme not in {"http", "https"}
            or not url.netloc
            or url.path not in {"", "/"}
            or url.username is not None
            or url.query
            or url.fragment
        ):
            raise ValueError("Configure a loopback Ollama URL, such as http://127.0.0.1:11434")
        return value

    @property
    def whisper_model_path(self) -> Path:
        if self.whisper_model_dir is not None:
            return self.whisper_model_dir.expanduser()
        name = quote(self.whisper_model, safe="")
        return REPO_ROOT / ".pilot-cache" / "whisper" / f"model-{name}"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def pack_dir(self) -> Path:
        return self.packs_dir / self.pack

    @property
    def bible_path(self) -> Path:
        return self.pack_dir / "data" / "web.json"

    @property
    def letterhead_path(self) -> Path:
        return self.pack_dir / "templates" / "letterhead.docx"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.files_dir, self.outputs_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir = s.data_dir.expanduser()
    return s
