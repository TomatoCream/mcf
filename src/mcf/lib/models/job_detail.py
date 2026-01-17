"""
Job Detail models following the MCF API JSON structure.
Extended models for the job details endpoint.
"""

from pydantic import BaseModel, ConfigDict

from .models import (
    Address,
    Category,
    EmploymentType,
    FlexibleWorkArrangement,
    PositionLevel,
    Scheme,
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


# ==============================================================================
# Job Detail Specific Models
# ==============================================================================


class DetailSkill(_Base):
    """Extended skill model with isKeySkill and confidence fields."""

    uuid: str
    skill: str
    # API sometimes returns null; treat as False/unknown but do not fail validation.
    isKeySkill: bool | None = False
    confidence: float | None = None

class Badge(_Base):
    badgeType: str | None = None
    expiryDate: str | None = None


class DetailSalaryType(_Base):
    """Salary type with id field."""

    id: int
    salaryType: str


class DetailSalary(_Base):
    minimum: int | None = None
    maximum: int | None = None
    type: DetailSalaryType | None = None


class DetailJobStatus(_Base):
    """Job status with integer id (differs from search model)."""

    id: int
    jobStatus: str


class DetailLink(_Base):
    href: str


class CompanyLinks(_Base):
    self: DetailLink | None = None
    jobs: DetailLink | None = None
    addresses: DetailLink | None = None
    schemes: DetailLink | None = None


class DetailCompany(_Base):
    """Extended company model with full details."""

    uen: str | None = None
    name: str | None = None
    description: str | None = None
    ssicCode: str | None = None
    ssicCode2020: str | None = None
    employeeCount: int | None = None
    companyUrl: str | None = None
    lastSyncDate: str | None = None
    badges: list[Badge] = []
    logoFileName: str | None = None
    logoUploadPath: str | None = None
    responsiveEmployer: dict | None = None
    _links: CompanyLinks | None = None


class DetailMetadata(_Base):
    """Extended metadata model with full job detail fields."""

    jobPostId: str
    deletedAt: str | None = None
    createdBy: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    emailRecipient: str | None = None
    editCount: int = 0
    repostCount: int = 0
    totalNumberOfView: int = 0
    newPostingDate: str | None = None
    originalPostingDate: str | None = None
    expiryDate: str | None = None
    totalNumberJobApplication: int = 0
    isPostedOnBehalf: bool = False
    isHideSalary: bool = False
    isHideCompanyAddress: bool = False
    isHideHiringEmployerName: bool = False
    isHideEmployerName: bool = False
    jobDetailsUrl: str | None = None


class ScreeningQuestion(_Base):
    """Screening question for job applications."""

    id: int | None = None
    question: str | None = None
    answerType: str | None = None
    isRequired: bool = False


class JobDetailLinks(_Base):
    self: DetailLink | None = None
    screeningQuestions: DetailLink | None = None


class JobDetail(_Base):
    """Full job detail model from the details endpoint."""

    uuid: str
    title: str
    sourceCode: str | None = None
    description: str | None = None
    minimumYearsExperience: int | None = None
    shiftPattern: str | None = None
    otherRequirements: str | None = None
    ssocCode: str | None = None
    occupationId: str | None = None
    ssocVersion: str | None = None
    workingHours: str | None = None
    numberOfVacancies: int | None = None
    psdUrl: str | None = None
    ssecEqa: str | None = None
    ssecFos: str | None = None

    # Nested models
    skills: list[DetailSkill] = []
    schemes: list[Scheme] = []
    flexibleWorkArrangements: list[FlexibleWorkArrangement] = []
    categories: list[Category] = []
    employmentTypes: list[EmploymentType] = []
    positionLevels: list[PositionLevel] = []
    status: DetailJobStatus | None = None
    postedCompany: DetailCompany | None = None
    hiringCompany: DetailCompany | None = None
    screeningQuestions: list[ScreeningQuestion] = []
    address: Address | None = None
    metadata: DetailMetadata | None = None
    salary: DetailSalary | None = None
    _links: JobDetailLinks | None = None

