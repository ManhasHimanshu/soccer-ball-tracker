import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getVideoStatus, WS_URL } from '../config/api'
import LoadingSpinner from '../components/LoadingSpinner'

const STATE_MESSAGES = {
  EXTRACTING_FRAMES: {
    label: 'Extracting frames',
    description: 'Breaking your video into individual frames...',
    step: 1
  },
  RUNNING_INFERENCE: {
    label: 'Running inference',
    description: 'YOLOv8 is detecting the ball in each frame...',
    step: 2
  },
  COMPLETE: {
    label: 'Complete',
    description: 'Processing finished successfully!',
    step: 3
  },
  FAILED: {
    label: 'Failed',
    description: 'Something went wrong during processing.',
    step: 0
  }
}

function StatusPage() {
  const { videoId } = useParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)

  useEffect(() => {
  let cancelled = false

  // One initial fetch: pushes only cover transitions AFTER we connect,
  // so a page opened mid-pipeline needs current state once.
  const fetchInitial = async () => {
    try {
      const data = await getVideoStatus(videoId)
      if (!cancelled) setStatus(data)
    } catch (err) {
      // 404 = pipeline hasn't written STATUS yet; the socket will tell us when it does
      if (err.response?.status !== 404 && !cancelled) {
        setError('Failed to fetch status. Please refresh.')
      }
    }
  }

  const ws = new WebSocket(WS_URL)
  wsRef.current = ws

  ws.onopen = () => {
    // Fetch AFTER the socket is open: no gap where an update could slip past us
    fetchInitial()
  }

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    if (msg.videoId !== videoId) return  // broadcast carries all videos; keep ours
    setStatus({
      state: msg.state,
      error: msg.error,
      updatedAt: new Date().toISOString()
    })
  }

  ws.onerror = () => {
    if (!cancelled) setError('Live connection failed. Please refresh.')
  }

  return () => {
    cancelled = true
    ws.close()
  }
}, [videoId])

useEffect(() => {
  if (status?.state === 'COMPLETE') {
    const t = setTimeout(() => navigate(`/results/${videoId}`), 1500)
    return () => clearTimeout(t)
  }
}, [status, videoId, navigate])

  const currentStep = status ? (STATE_MESSAGES[status.state]?.step || 0) : 0

  const steps = [
    { label: 'Extracting frames', step: 1 },
    { label: 'Running inference', step: 2 },
    { label: 'Complete', step: 3 }
  ]

  return (
    <div className="max-w-lg mx-auto">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">
          Processing Video
        </h1>
        <p className="text-gray-500 text-sm mb-6 font-mono">
          {videoId}
        </p>

        {/* Step indicators */}
        <div className="mb-8">
          {steps.map(({ label, step }) => {
            const isDone = currentStep > step
            const isActive = currentStep === step
            const isPending = currentStep < step

            return (
              <div key={step} className="flex items-center gap-3 mb-3">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0 ${
                  isDone
                    ? 'bg-green-500 text-white'
                    : isActive
                    ? 'bg-blue-500 text-white animate-pulse'
                    : 'bg-gray-100 text-gray-400'
                }`}>
                  {isDone ? '✓' : step}
                </div>
                <span className={`text-sm font-medium ${
                  isDone
                    ? 'text-green-600'
                    : isActive
                    ? 'text-blue-600'
                    : 'text-gray-400'
                }`}>
                  {label}
                </span>
              </div>
            )
          })}
        </div>

        {/* Current status message */}
        {!status && !error && (
          <LoadingSpinner message="Waiting for pipeline to start..." />
        )}

        {status && status.state !== 'COMPLETE' && status.state !== 'FAILED' && (
          <LoadingSpinner
            message={STATE_MESSAGES[status.state]?.description || 'Processing...'}
          />
        )}

        {status?.state === 'COMPLETE' && (
          <div className="text-center py-4">
            <div className="text-4xl mb-2">✅</div>
            <p className="text-green-600 font-medium">
              Processing complete! Redirecting to results...
            </p>
          </div>
        )}

        {status?.state === 'FAILED' && (
          <div className="text-center py-4">
            <div className="text-4xl mb-2">❌</div>
            <p className="text-red-600 font-medium mb-1">Processing failed</p>
            <p className="text-sm text-gray-500">{status.error || 'Unknown error'}</p>
            <button
              onClick={() => navigate('/upload')}
              className="mt-4 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg transition-colors"
            >
              Try another video
            </button>
          </div>
        )}

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {/* Last updated */}
        {status?.updatedAt && (
          <p className="text-xs text-gray-400 text-center mt-4">
            Last updated: {new Date(status.updatedAt).toLocaleTimeString()}
          </p>
        )}
      </div>
    </div>
  )
}

export default StatusPage