'use client'

import { useEffect, useState } from 'react'
import { jobsApi, matchesApi, profileApi, type Match, type Profile } from '@/lib/api'

export default function Home() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [matches, setMatches] = useState<Match[]>([])
  const [loading, setLoading] = useState(true)
  const [processingResume, setProcessingResume] = useState(false)

  useEffect(() => {
    loadProfile()
  }, [])

  const loadProfile = async () => {
    try {
      const profileData = await profileApi.get()
      setProfile(profileData)
    } catch (error) {
      console.error('Failed to load profile:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleProcessResume = async () => {
    try {
      setProcessingResume(true)
      await profileApi.processResume()
      await loadProfile()
      alert('Resume processed successfully!')
    } catch (error: any) {
      alert(`Failed to process resume: ${error.response?.data?.detail || error.message}`)
    } finally {
      setProcessingResume(false)
    }
  }

  const handleFindMatches = async () => {
    try {
      setLoading(true)
      const matchesData = await matchesApi.get(true, 25)
      setMatches(matchesData.matches || [])
    } catch (error: any) {
      console.error('Failed to load matches:', error)
      alert(`Failed to load matches: ${error.response?.data?.detail || error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleInteraction = async (jobUuid: string, interactionType: string) => {
    try {
      await jobsApi.markInteraction(jobUuid, interactionType)
      // Reload matches to reflect the change
      await handleFindMatches()
    } catch (error: any) {
      console.error('Failed to mark interaction:', error)
      alert(`Failed to mark interaction: ${error.response?.data?.detail || error.message}`)
    }
  }

  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return 'N/A'
    return new Date(dateStr).toLocaleDateString()
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
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
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {processingResume ? 'Processing...' : 'Process Resume'}
              </button>
            </div>
          ) : (
            <div className="text-center py-4 text-gray-500">Failed to load profile</div>
          )}
        </div>

        {/* Find Matches Section */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-semibold">Job Matches</h2>
            <button
              onClick={handleFindMatches}
              disabled={loading || !profile?.profile}
              className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Find Matches
            </button>
          </div>
          {matches.length > 0 && (
            <div className="text-sm text-gray-600 mb-4">
              Found {matches.length} matching jobs (sorted by similarity, then recency)
            </div>
          )}
        </div>

        {/* Matches List */}
        {matches.length > 0 && (
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-2xl font-semibold mb-4">Matched Jobs</h2>
            <div className="space-y-4">
              {matches.map((job) => (
                <div
                  key={job.job_uuid}
                  className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <h3 className="text-xl font-semibold text-gray-900 mb-2">{job.title}</h3>
                      <div className="text-sm text-gray-600 mb-2">
                        {job.company_name && <span className="mr-4">Company: {job.company_name}</span>}
                        {job.location && <span className="mr-4">Location: {job.location}</span>}
                        {job.last_seen_at && (
                          <span className="text-gray-500">Posted: {formatDate(job.last_seen_at)}</span>
                        )}
                      </div>
                      {job.job_url && (
                        <a
                          href={job.job_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 underline text-sm"
                        >
                          View full job description on MyCareersFuture →
                        </a>
                      )}
                    </div>
                    <div className="ml-4 text-right">
                      <div className="text-lg font-bold text-green-600 mb-2">
                        {(job.similarity_score * 100).toFixed(1)}% match
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2 mt-4 pt-4 border-t border-gray-200">
                    <button
                      onClick={() => handleInteraction(job.job_uuid, 'viewed')}
                      className="px-3 py-1 bg-blue-100 text-blue-700 rounded text-sm hover:bg-blue-200"
                    >
                      Viewed
                    </button>
                    <button
                      onClick={() => handleInteraction(job.job_uuid, 'saved')}
                      className="px-3 py-1 bg-yellow-100 text-yellow-700 rounded text-sm hover:bg-yellow-200"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => handleInteraction(job.job_uuid, 'applied')}
                      className="px-3 py-1 bg-green-100 text-green-700 rounded text-sm hover:bg-green-200"
                    >
                      Applied
                    </button>
                    <button
                      onClick={() => handleInteraction(job.job_uuid, 'dismissed')}
                      className="px-3 py-1 bg-red-100 text-red-700 rounded text-sm hover:bg-red-200"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {matches.length === 0 && !loading && (
          <div className="bg-white rounded-lg shadow-md p-6 text-center text-gray-500">
            No matches found. Click "Find Matches" to search for jobs matching your resume.
          </div>
        )}
      </div>
    </main>
  )
}
