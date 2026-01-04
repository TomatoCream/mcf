"""
Models strictly following the MCF API JSON structure.
Designed for JSON serialization and pandas/polars/pyarrow compatibility.
"""

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


# ==============================================================================
# Job/Search Models
# ==============================================================================


class Skill(_Base):
    uuid: str
    skill: str


class ResponsiveEmployer(_Base):
    isResponsive: bool


class Company(_Base):
    uen: str | None = None
    logoFileName: str | None = None
    name: str | None = None
    logoUploadPath: str | None = None
    responsiveEmployer: ResponsiveEmployer | None = None


class Category(_Base):
    category: str
    id: int


class FlexibleWorkArrangement(_Base):
    arrangement: str | None = None
    id: int


class JobMetadata(_Base):
    jobPostId: str
    isHideHiringEmployerName: bool
    isPostedOnBehalf: bool
    totalNumberJobApplication: int
    updatedAt: str
    newPostingDate: str
    jobDetailsUrl: str
    isHideSalary: bool


class EmploymentType(_Base):
    employmentType: str
    id: int


class SubScheme(_Base):
    name: str | None = None
    id: int


class Scheme(_Base):
    name: str | None = None
    expiryDate: str | None = None
    subScheme: SubScheme | None = None


class District(_Base):
    location: str | None = None
    regionId: str | None = None
    region: str | None = None
    sectors: list[str] = []
    id: int


class Address(_Base):
    street: str | None = None
    isOverseas: bool | None = None
    postalCode: str | None = None
    lat: float | None = None
    block: str | None = None
    lng: float | None = None
    building: str | None = None
    floor: str | None = None
    unit: str | None = None
    overseasCountry: str | None = None
    foreignAddress1: str | None = None
    foreignAddress2: str | None = None
    districts: list[District] = []


class SalaryType(_Base):
    salaryType: str


class Salary(_Base):
    minimum: int | None = None
    maximum: int | None = None
    type: SalaryType | None = None


class PositionLevel(_Base):
    id: int
    position: str


class JobStatus(_Base):
    jobStatus: str
    id: int


class Job(_Base):
    uuid: str
    title: str
    score: float = 0.0
    retriever_score: float = 0.0
    recency_score: float = 0.0
    title_match_score: float = 0.0
    skills_match_score: float = 0.0
    company_match_score: float = 0.0
    job_role_score: float = 0.0
    shiftPattern: str | None = None
    skills: list[Skill] = []
    hiringCompany: Company | None = None
    postedCompany: Company | None = None
    categories: list[Category] = []
    flexibleWorkArrangements: list[FlexibleWorkArrangement] = []
    metadata: JobMetadata | None = None
    employmentTypes: list[EmploymentType] = []
    schemes: list[Scheme] = []
    address: Address | None = None
    salary: Salary | None = None
    positionLevels: list[PositionLevel] = []
    status: JobStatus | None = None


# ==============================================================================
# Search Response Models
# ==============================================================================


class SearchLink(_Base):
    href: str


class SearchLinks(_Base):
    next: SearchLink | None = None
    self: SearchLink | None = None
    first: SearchLink | None = None
    last: SearchLink | None = None


class SearchResponse(_Base):
    _links: SearchLinks | None = None
    searchRankingId: str | None = None
    results: list[Job] = []
    total: int
    countWithoutFilters: int


# ==============================================================================
# Profile/Common Data Models
# ==============================================================================


class EmploymentTypeOption(_Base):
    id: str
    name: str


class Ssoc(_Base):
    ssocTitle: str
    ssoc: str


class Ssic(_Base):
    code: str
    description: str


class Country(_Base):
    code: str
    description: str
    codeNumber: str


class EmploymentStatus(_Base):
    id: str
    description: str


class SsecEqa(_Base):
    code: str
    description: str


class SsecFos(_Base):
    code: str
    description: str


class CommonData(_Base):
    employmentTypes: list[EmploymentTypeOption] = []
    ssocList: list[Ssoc] = []
    ssicList: list[Ssic] = []
    countriesList: list[Country] = []
    employmentStatusList: list[EmploymentStatus] = []
    ssecEqaList: list[SsecEqa] = []
    ssecFosList: list[SsecFos] = []


class ProfileData(_Base):
    common: CommonData | None = None


class ProfileResponse(_Base):
    data: ProfileData | None = None
