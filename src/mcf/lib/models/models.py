"""Pydantic models for MyCareersFuture API responses."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================


class SalaryType(str, Enum):
    """Salary payment frequency."""

    MONTHLY = "Monthly"
    YEARLY = "Yearly"
    HOURLY = "Hourly"
    DAILY = "Daily"


class JobStatus(str, Enum):
    """Job posting status."""

    OPEN = "Open"
    REOPEN = "Re-open"
    CLOSED = "Closed"


# ============================================================================
# Search API Models (REST)
# ============================================================================


class Category(BaseModel):
    """Job category."""

    id: int
    category: str


class ResponsiveEmployer(BaseModel):
    """Employer responsiveness indicator."""

    is_responsive: bool = Field(alias="isResponsive")


class Company(BaseModel):
    """Company information."""

    name: str
    uen: str | None = None
    logo_upload_path: str | None = Field(None, alias="logoUploadPath")
    logo_file_name: str | None = Field(None, alias="logoFileName")
    responsive_employer: ResponsiveEmployer | None = Field(
        None, alias="responsiveEmployer"
    )


class SalaryTypeInfo(BaseModel):
    """Salary type details."""

    salary_type: SalaryType = Field(alias="salaryType")


class Salary(BaseModel):
    """Salary range information."""

    type: SalaryTypeInfo | None = None
    minimum: int | None = None
    maximum: int | None = None

    @property
    def display(self) -> str:
        """Format salary for display."""
        if self.minimum is None and self.maximum is None:
            return "Not specified"
        freq = self.type.salary_type.value if self.type else "Monthly"
        if self.minimum == self.maximum:
            return f"${self.minimum:,}/{freq}"
        min_str = f"${self.minimum:,}" if self.minimum else "?"
        max_str = f"${self.maximum:,}" if self.maximum else "?"
        return f"{min_str} - {max_str}/{freq}"


class District(BaseModel):
    """Location district information."""

    id: int
    region_id: str = Field(alias="regionId")
    region: str
    location: str
    sectors: list[str] = []


class Address(BaseModel):
    """Job location address."""

    is_overseas: bool = Field(alias="isOverseas")
    postal_code: str | None = Field(None, alias="postalCode")
    overseas_country: str | None = Field(None, alias="overseasCountry")
    lat: float | None = None
    lng: float | None = None
    block: str | None = None
    street: str | None = None
    building: str | None = None
    floor: str | None = None
    unit: str | None = None
    districts: list[District] = []

    @property
    def display(self) -> str:
        """Format address for display."""
        if self.is_overseas:
            return self.overseas_country or "Overseas"
        parts = [p for p in [self.block, self.street, self.building] if p]
        if parts:
            return ", ".join(parts)
        if self.districts:
            return self.districts[0].location
        return "Singapore"


class EmploymentType(BaseModel):
    """Type of employment."""

    id: int
    employment_type: str = Field(alias="employmentType")


class PositionLevel(BaseModel):
    """Position seniority level."""

    id: int
    position: str


class Skill(BaseModel):
    """Required skill."""

    uuid: str
    skill: str


class JobMetadata(BaseModel):
    """Job posting metadata."""

    job_details_url: str = Field(alias="jobDetailsUrl")
    job_post_id: str = Field(alias="jobPostId")
    new_posting_date: date = Field(alias="newPostingDate")
    updated_at: datetime = Field(alias="updatedAt")
    is_hide_salary: bool = Field(alias="isHideSalary")
    is_hide_hiring_employer_name: bool = Field(alias="isHideHiringEmployerName")
    is_posted_on_behalf: bool = Field(alias="isPostedOnBehalf")
    total_number_job_application: int = Field(alias="totalNumberJobApplication")


class JobStatusInfo(BaseModel):
    """Job status details."""

    id: str
    job_status: JobStatus = Field(alias="jobStatus")


class FlexibleWorkArrangement(BaseModel):
    """Flexible work arrangement type."""

    id: int | None = None
    arrangement: str | None = None


class JobPosting(BaseModel):
    """A single job posting from search results."""

    uuid: str
    title: str
    score: float = 0
    retriever_score: float = 0
    recency_score: float = 0
    skills_match_score: float = 0
    company_match_score: float = 0
    job_role_score: float = 0
    title_match_score: float = 0

    categories: list[Category] = []
    posted_company: Company = Field(alias="postedCompany")
    hiring_company: Company | None = Field(None, alias="hiringCompany")
    salary: Salary | None = None
    address: Address | None = None
    employment_types: list[EmploymentType] = Field([], alias="employmentTypes")
    position_levels: list[PositionLevel] = Field([], alias="positionLevels")
    flexible_work_arrangements: list[FlexibleWorkArrangement] = Field(
        [], alias="flexibleWorkArrangements"
    )
    skills: list[Skill] = []
    schemes: list[str] = []
    shift_pattern: str | None = Field(None, alias="shiftPattern")
    status: JobStatusInfo | None = None
    metadata: JobMetadata

    @property
    def company_name(self) -> str:
        """Get the effective company name."""
        if self.hiring_company and not self.metadata.is_hide_hiring_employer_name:
            return self.hiring_company.name
        return self.posted_company.name

    @property
    def location(self) -> str:
        """Get formatted location."""
        return self.address.display if self.address else "Singapore"


class PaginationLink(BaseModel):
    """Pagination link."""

    href: str


class PaginationLinks(BaseModel):
    """Pagination navigation links."""

    self_link: PaginationLink = Field(alias="self")
    first: PaginationLink | None = None
    next_link: PaginationLink | None = Field(None, alias="next")
    last: PaginationLink | None = None


class JobSearchResponse(BaseModel):
    """Response from the job search API."""

    links: PaginationLinks = Field(alias="_links")
    search_ranking_id: str = Field(alias="searchRankingId")
    results: list[JobPosting]
    total: int
    count_without_filters: int = Field(alias="countWithoutFilters")


# ============================================================================
# Profile/Metadata API Models (GraphQL)
# ============================================================================


class MetadataEmploymentType(BaseModel):
    """Employment type metadata."""

    id: str
    name: str


class SSOC(BaseModel):
    """Singapore Standard Occupational Classification."""

    ssoc: str
    ssoc_title: str = Field(alias="ssocTitle")


class SSIC(BaseModel):
    """Singapore Standard Industrial Classification."""

    code: str
    description: str


class Country(BaseModel):
    """Country information."""

    code: str
    code_number: str = Field(alias="codeNumber")
    description: str


class EmploymentStatus(BaseModel):
    """Employment status option."""

    id: str
    description: str


class SSECEqa(BaseModel):
    """Singapore Standard Educational Classification - EQA."""

    code: str
    description: str


class SSECFos(BaseModel):
    """Singapore Standard Educational Classification - Field of Study."""

    code: str
    description: str


class CommonMetadata(BaseModel):
    """Common metadata from profile API."""

    employment_types: list[MetadataEmploymentType] = Field(alias="employmentTypes")
    ssoc_list: list[SSOC] = Field(alias="ssocList")
    ssic_list: list[SSIC] = Field(alias="ssicList")
    countries_list: list[Country] = Field(alias="countriesList")
    employment_status_list: list[EmploymentStatus] = Field(alias="employmentStatusList")
    ssec_eqa_list: list[SSECEqa] = Field(alias="ssecEqaList")
    ssec_fos_list: list[SSECFos] = Field(alias="ssecFosList")


class ProfileData(BaseModel):
    """Profile API data container."""

    common: CommonMetadata


class ProfileResponse(BaseModel):
    """Response from the profile/metadata GraphQL API."""

    data: ProfileData


# ============================================================================
# Search Request Models
# ============================================================================


class SearchFilters(BaseModel):
    """Filters for job search."""

    keywords: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    employment_types: list[str] | None = None
    categories: list[str] | None = None
    posting_company: list[str] | None = None
    page: int = 0
    limit: int = 20

    model_config = {"populate_by_name": True}

