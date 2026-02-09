"""Configuration management for RFMP daemon."""

import os
import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from pathlib import Path


class NodeConfig(BaseSettings):
    """Node configuration."""
    callsign: str = Field(default="N0CALL", description="Amateur radio callsign")
    ssid: int = Field(default=0, ge=0, le=15, description="SSID (0-15)")

    @field_validator('callsign')
    @classmethod
    def validate_callsign(cls, v):
        """Validate callsign format."""
        v = v.upper()
        if len(v) > 6 or len(v) < 1:
            raise ValueError("Callsign must be 1-6 characters")
        if not v.replace('-', '').isalnum():
            raise ValueError("Callsign must be alphanumeric")
        return v


class NetworkConfig(BaseSettings):
    """Network configuration."""
    direwolf_host: str = Field(default="127.0.0.1", description="Direwolf TCP host")
    direwolf_port: int = Field(default=8001, description="Direwolf TCP port")
    reconnect_interval: int = Field(default=5, ge=1, description="Reconnect interval in seconds")
    offline_mode: bool = Field(default=False, description="Run without Direwolf connection")


class ProtocolConfig(BaseSettings):
    """Protocol configuration."""
    fragment_threshold: int = Field(default=200, ge=50, le=500, description="Fragment threshold in bytes")


class TimingConfig(BaseSettings):
    """Timing configuration."""
    base_delay: float = Field(default=0.2, ge=0.0, description="Base transmission delay")
    jitter: float = Field(default=0.4, ge=0.0, description="Random jitter range")
    priority_step: float = Field(default=0.35, ge=0.0, description="Delay per priority level")


class SyncConfig(BaseSettings):
    """Synchronization configuration."""
    window_duration: int = Field(default=600, ge=60, description="Bloom filter window duration")
    window_count: int = Field(default=3, ge=1, le=5, description="Number of windows")
    bloom_bits: int = Field(default=256, description="Bloom filter size in bits")
    bloom_hashes: int = Field(default=3, ge=1, le=10, description="Number of hash functions")
    sync_interval: int = Field(default=60, ge=10, description="SYNC broadcast interval")


class RateLimitConfig(BaseSettings):
    """Rate limiting configuration."""
    max_req_per_min: int = Field(default=6, ge=1, description="Max REQ frames per minute")
    initial_backoff: int = Field(default=30, ge=1, description="Initial backoff seconds")
    max_backoff: int = Field(default=600, ge=60, description="Maximum backoff seconds")
    max_retries: int = Field(default=4, ge=1, description="Maximum retries per message")


class StorageConfig(BaseSettings):
    """Storage configuration."""
    database_path: str = Field(default="~/rfmpd/messages.db", description="Database file path")

    @field_validator('database_path')
    @classmethod
    def expand_path(cls, v):
        """Expand user path."""
        return os.path.expanduser(v)


class APIConfig(BaseSettings):
    """API configuration."""
    host: str = Field(default="0.0.0.0", description="API bind address")
    port: int = Field(default=8080, ge=1, le=65535, description="API port")
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins"
    )


class LoggingConfig(BaseSettings):
    """Logging configuration."""
    level: str = Field(default="INFO", description="Log level")
    file: str = Field(default="~/rfmpd/rfmpd.log", description="Log file path")
    max_size: int = Field(default=10485760, description="Max log file size")
    backup_count: int = Field(default=5, description="Number of backup files")

    @field_validator('file')
    @classmethod
    def expand_path(cls, v):
        """Expand user path."""
        return os.path.expanduser(v)

    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v


class Config(BaseSettings):
    """Main configuration class."""
    node: NodeConfig = Field(default_factory=NodeConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    protocol: ProtocolConfig = Field(default_factory=ProtocolConfig)
    timing: TimingConfig = Field(default_factory=TimingConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    model_config = SettingsConfigDict(
        env_prefix='RFMPD_',
        env_nested_delimiter='__',
        case_sensitive=False
    )

    @classmethod
    def load_from_file(cls, config_path: Optional[str] = None) -> 'Config':
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config file (uses default locations if None)

        Returns:
            Loaded configuration
        """
        if config_path:
            config_file = Path(config_path)
        else:
            # Try default locations
            possible_paths = [
                Path("config.yaml"),
                Path("~/rfmpd/config.yaml").expanduser(),
                Path("/etc/rfmpd/config.yaml"),
            ]

            config_file = None
            for path in possible_paths:
                if path.exists():
                    config_file = path
                    break

        # Load from file if found
        if config_file and config_file.exists():
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f)

            # Create nested config objects
            if data:
                config_dict = {}
                for section, values in data.items():
                    if isinstance(values, dict):
                        config_dict[section] = values

                return cls(**config_dict)

        # Return default config if no file found
        return cls()

    def save_to_file(self, config_path: str):
        """
        Save configuration to YAML file.

        Args:
            config_path: Path to save config file
        """
        # Convert to dictionary
        config_dict = {
            'node': self.node.model_dump(),
            'network': self.network.model_dump(),
            'protocol': self.protocol.model_dump(),
            'timing': self.timing.model_dump(),
            'sync': self.sync.model_dump(),
            'rate_limit': self.rate_limit.model_dump(),
            'storage': self.storage.model_dump(),
            'api': self.api.model_dump(),
            'logging': self.logging.model_dump()
        }

        # Ensure directory exists
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Write YAML file
        with open(config_file, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)