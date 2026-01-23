"""Configuration management for the triage agent."""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI Configuration
    openai_api_key: str

    # Model Configuration
    classification_model: str = "gpt-4o-mini"
    generation_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"

    # Temperature Configuration
    classification_temperature: float = 0.0  # Deterministic for classification
    generation_temperature: float = 0.3  # Low temperature for consistent, grounded responses

    # Application Configuration
    log_level: str = "INFO"
    environment: str = "development"

    # Threshold Configuration
    min_confidence_threshold: float = 0.7
    high_confidence_threshold: float = 0.85
    high_risk_threshold: float = 0.7
    template_similarity_threshold: float = 0.9
    min_retrieval_score: float = 0.75

    # PII Risk Weights
    high_risk_pii_weight: float = 0.3
    medium_risk_pii_weight: float = 0.15
    max_pii_contribution: float = 0.4

    # Confidence Penalty
    confidence_penalty_multiplier: float = 0.2

    # PII-related confidence adjustment
    pii_confidence_reduction: float = 0.2
    pii_medium_confidence_threshold: float = 0.85

    # Vector Database Configuration
    vector_db_path: str = "./data/vector_db"
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k_retrieval: int = 3

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    max_input_length: int = 2000
    min_input_length: int = 10
    max_output_length: int = 1000

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
