import axios from 'axios'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface Job {
  job_uuid: string
  title: string
  company_name: string | null
  location: string | null
  job_url: string | null
  similarity_score?: number
  last_seen_at?: string
  interactions?: string[]
}

export interface Match {
  job_uuid: string
  title: string
  company_name: string | null
  location: string | null
  job_url: string | null
  similarity_score: number
  last_seen_at?: string
}

export interface Profile {
  user_id: string
  profile: any
  resume_path: string
  resume_exists: boolean
}

// Jobs API
export const jobsApi = {
  list: async (limit: number = 100, offset: number = 0, keywords?: string, excludeInteracted: boolean = true) => {
    const params = new URLSearchParams({ 
      limit: limit.toString(), 
      offset: offset.toString(),
      exclude_interacted: excludeInteracted.toString()
    })
    if (keywords) params.append('keywords', keywords)
    const response = await api.get(`/api/jobs?${params}`)
    return response.data
  },
  get: async (jobUuid: string) => {
    const response = await api.get(`/api/jobs/${jobUuid}`)
    return response.data
  },
  markInteraction: async (jobUuid: string, interactionType: string) => {
    const response = await api.post(`/api/jobs/${jobUuid}/interact`, null, {
      params: { interaction_type: interactionType }
    })
    return response.data
  },
}

// Profile API
export const profileApi = {
  get: async () => {
    const response = await api.get('/api/profile')
    return response.data as Profile
  },
  processResume: async () => {
    const response = await api.post('/api/profile/process-resume')
    return response.data
  },
}

// Matches API
export const matchesApi = {
  get: async (
    excludeInteracted: boolean = true, 
    topK: number = 25,
    minSimilarity?: number,
    maxDaysOld?: number
  ) => {
    const params = new URLSearchParams({
      exclude_interacted: excludeInteracted.toString(),
      top_k: topK.toString()
    })
    if (minSimilarity !== undefined) {
      params.append('min_similarity', minSimilarity.toString())
    }
    if (maxDaysOld !== undefined) {
      params.append('max_days_old', maxDaysOld.toString())
    }
    const response = await api.get(`/api/matches?${params}`)
    return response.data
  },
}
