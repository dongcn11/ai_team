from fastapi import APIRouter
from system_config import get_system_agents, get_profiles

router = APIRouter()


@router.get("/agents")
def list_system_agents():
    return get_system_agents()


@router.get("/profiles")
def list_profiles():
    return get_profiles()
