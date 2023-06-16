from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List


@dataclass
class PoolPartyProject:
    defaultLanguage: str
    title: str
    userGroups: []
    author: str = None
    availableLanguages: List[str] = field(default_factory=list)
    baseUrl: str = None
    contributor: str = None
    description: str = None
    enableSkosXl: bool = False
    enableWorkflow: bool = False
    idGeneration: str = "increment"
    incrementStart: int = 0
    license: str = None
    projectIdentifier: str = None
    publisher: str = None
    qualitySetting: str = "default"
    remoteRepositoryIRI: str = None
    repositoryType: str = "memory"
    snapshotInterval: int = -1
    subject: str = None
    worflowAssignee: str = None
    workflowState: str = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v}

