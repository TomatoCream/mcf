'use client'

import { useEffect, useState } from 'react'
import { jobsApi, matchesApi, profileApi, type Match, type Profile } from '@/lib/api'
import toast, { Toaster } from 'react-hot-toast'

export default function Home() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [matches, setMatches] = useState<Match[]>([])
  const [loading, setLoading] = useState(true)
  const [findingMatches, setFindingMatches] = useState(false)
  const [processingResume, setProcessingResume] = useState(false)
  const [loadingJobs, setLoadingJobs] = useState<Set<string>>(new Set())
  
  // Filter state
  const [filters, setFilters] = useState({
    minSimilarity: 0,
    maxDaysOld: null as number | null,
    topK: 25
  })

  useEffect(() => {
    loadProfile()
  }, [])

  const loadProfile = async () => {
    try {
      const profileData = await profileApi.get()
      setProfile(profileData)
    } catch (error) {
      console.error('Failed to load profile:', error)
      toast.error('Failed to load profile')
    } finally {
      setLoading(false)
    }
  }

  const handleProcessResume = async () => {
    try {
      setProcessingResume(true)
      await profileApi.processResume()
      await loadProfile()
      toast.success('Resume processed successfully!')
    } catch (error: any) {
      toast.error(`Failed to process resume: ${error.response?.data?.detail || error.message}`)
    } finally {
      setProcessingResume(false)
    }
  }

  const handleFindMatches = async () => {
    try {
      setFindingMatches(true)
      const matchesData = await matchesApi.get(
        true, 
        filters.topK,
        filters.minSimilarity / 100,
        filters.maxDaysOld || undefined
      )
      setMatches(matchesData.matches || [])
      toast.success(`Found ${matchesData.matches?.length || 0} matches`)
    } catch (error: any) {
      console.error('Failed to load matches:', error)
      toast.error(`Failed to load matches: ${error.response?.data?.detail || error.message}`)
    } finally {
      setFindingMatches(false)
    }
  }

  const handleInteraction = async (jobUuid: string, interactionType: string) => {
    // Optimistic update: remove from UI immediately
    const previousMatches = [...matches]
    setMatches(prev => prev.filter(job => job.job_uuid !== jobUuid))
    
    // Add to loading set
    setLoadingJobs(prev => new Set(prev).add(jobUuid))
    
    try {
      await jobsApi.markInteraction(jobUuid, interactionType)
      toast.success(`Job ${interactionType}`)
    } catch (error: any) {
      // Rollback on error
      setMatches(previousMatches)
      console.error('Failed to mark interaction:', error)
      toast.error(`Failed to mark interaction: ${error.response?.data?.detail || error.message}`)
    } finally {
      // Remove from loading set
      setLoadingJobs(prev => {
        const next = new Set(prev)
        next.delete(jobUuid)
        return next
      })
    }
  }

  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return 'N/A'
    return new Date(dateStr).toLocaleDateString()
  }
  
  const getDaysAgo = (dateStr: string | undefined) => {
    if (!dateStr) return null
    const days = Math.floor((Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24))
    return days
  }
  
  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600'
    if (score >= 0.6) return 'text-yellow-600'
    return 'text-gray-600'
  }
  
  const getScoreBgColor = (score: number) => {
    if (score >= 0.8) return 'bg-green-50 border-green-200'
    if (score >= 0.6) return 'bg-yellow-50 border-yellow-200'
    return 'bg-gray-50 border-gray-200'
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold mb-8 text-gray-900">MCF Job Matcher</h1>

        {/* Resume Status Section */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-2xl font-semibold mb-4">Resume Status</h2>
          {loading ? (
            <div className="text-center py-4">Loading...</div>
          ) : profile ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <div className="text-sm text-gray-600">Resume File</div>
                  <div className="text-lg font-medium">{profile.resume_path}</div>
                </div>
                <div>
                  {profile.resume_exists ? (
                    <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
                      Found
                    </span>
                  ) : (
                    <span className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm font-medium">
                      Not Found
                    </span>
                  )}
                </div>
              </div>
              {profile.profile ? (
                <div className="text-sm text-gray-600">
                  Profile loaded: {profile.profile.profile_id || 'N/A'}
                </div>
              ) : (
                <div className="text-sm text-yellow-600">
                  No profile found. Process your resume to create a profile.
                </div>
              )}
              <button
                onClick={handleProcessResume}
                disabled={!profile.resume_exists || processingResume}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {processingResume ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Processing...
                  </span>
                ) : 'Process Resume'}
              </button>
            </div>
          ) : (
            <div className="text-center py-4 text-gray-500">Failed to load profile</div>
          )}
        </div>

        {/* Filter & Find Matches Section */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-semibold">Job Matches</h2>
            <button
              onClick={handleFindMatches}
              disabled={findingMatches || !profile?.profile}
              className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {findingMatches ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Finding...
                </span>
              ) : 'Find Matches'}
            </button>
          </div>
          
          {/* Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 p-4 bg-gray-50 rounded-lg">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Min Match %: <span className="text-blue-600 font-bold">{filters.minSimilarity}%</span>
              </label>
              <input
                type="range"
                min="0"
                max="100"
                value={filters.minSimilarity}
                onChange={(e) => setFilters({...filters, minSimilarity: parseInt(e.target.value)})}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Max Days Old
              </label>
              <input
                type="number"
                placeholder="No limit"
                value={filters.maxDaysOld || ''}
                onChange={(e) => setFilters({...filters, maxDaysOld: e.target.value ? parseInt(e.target.value) : null})}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Number of Results
              </label>
              <input
                type="number"
                min="1"
                max="100"
                value={filters.topK}
                onChange={(e) => setFilters({...filters, topK: parseInt(e.target.value) || 25})}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
              />
            </div>
          </div>
          
          {matches.length > 0 && (
            <div className="text-sm text-gray-600">
              Showing {matches.length} matching jobs (sorted by similarity, then recency)
            </div>
          )}
        </div>

        {/* Matches List */}
        {matches.length > 0 && (
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-2xl font-semibold mb-4">Matched Jobs</h2>
            <div className="space-y-4">
              {matches.map((job) => {
                const daysAgo = getDaysAgo(job.last_seen_at)
                const isLoading = loadingJobs.has(job.job_uuid)
                return (
                  <div
                    key={job.job_uuid}
                    className={`border-2 rounded-lg p-5 transition-all ${
                      isLoading ? 'opacity-50' : 'hover:shadow-lg'
                    } ${getScoreBgColor(job.similarity_score)}`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="text-xl font-bold text-gray-900">{job.title}</h3>
                          {daysAgo !== null && (
                            <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                              daysAgo <= 7 ? 'bg-green-100 text-green-800' :
                              daysAgo <= 30 ? 'bg-yellow-100 text-yellow-800' :
                              'bg-gray-100 text-gray-800'
                            }`}>
                              {daysAgo === 0 ? 'Today' : daysAgo === 1 ? '1 day ago' : `${daysAgo} days ago`}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-700 mb-3 space-y-1">
                          {job.company_name && (
                            <div className="flex items-center gap-2">
                              <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                              </svg>
                              <span className="font-medium">{job.company_name}</span>
                            </div>
                          )}
                          {job.location && (
                            <div className="flex items-center gap-2">
                              <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                              </svg>
                              <span>{job.location}</span>
                            </div>
                          )}
                        </div>
                        {job.job_url && (
                          <a
                            href={job.job_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 text-blue-600 hover:text-blue-800 font-medium text-sm transition-colors"
                          >
                            View full job description
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                          </a>
                        )}
                      </div>
                      <div className="ml-4 text-right">
                        <div className={`text-2xl font-bold mb-1 ${getScoreColor(job.similarity_score)}`}>
                          {(job.similarity_score * 100).toFixed(1)}%
                        </div>
                        <div className="text-xs text-gray-500 font-medium">match</div>
                      </div>
                    </div>
                    <div className="flex gap-2 mt-4 pt-4 border-t-2 border-gray-200">
                      <button
                        onClick={() => handleInteraction(job.job_uuid, 'viewed')}
                        disabled={isLoading}
                        className="px-4 py-2 bg-blue-100 text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        </svg>
                        Viewed
                      </button>
                      <button
                        onClick={() => handleInteraction(job.job_uuid, 'saved')}
                        disabled={isLoading}
                        className="px-4 py-2 bg-yellow-100 text-yellow-700 rounded-lg text-sm font-medium hover:bg-yellow-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                        </svg>
                        Save
                      </button>
                      <button
                        onClick={() => handleInteraction(job.job_uuid, 'applied')}
                        disabled={isLoading}
                        className="px-4 py-2 bg-green-100 text-green-700 rounded-lg text-sm font-medium hover:bg-green-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Applied
                      </button>
                      <button
                        onClick={() => handleInteraction(job.job_uuid, 'dismissed')}
                        disabled={isLoading}
                        className="px-4 py-2 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                        Dismiss
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {matches.length === 0 && !findingMatches && (
          <div className="bg-white rounded-lg shadow-md p-8 text-center">
            <svg className="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <p className="text-gray-500 text-lg">No matches found. Click "Find Matches" to search for jobs matching your resume.</p>
          </div>
        )}
      </div>
    </main>
  )
}
