import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { AdminRoute, ProtectedRoute } from './auth/guards'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { SetupPage } from './pages/SetupPage'
import { AdminPage } from './pages/AdminPage'
import { PlayPage } from './pages/PlayPage'
import { DailyPage } from './pages/DailyPage'
import { DuelLobbyPage } from './pages/DuelLobbyPage'
import { DuelPage } from './pages/DuelPage'
import { GamePage } from './pages/GamePage'
import { ResultPage } from './pages/ResultPage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { ProfilePage } from './pages/ProfilePage'
import { NotFoundPage } from './pages/NotFoundPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/setup" element={<SetupPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <HomePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/play"
          element={
            <ProtectedRoute>
              <PlayPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/daily"
          element={
            <ProtectedRoute>
              <DailyPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/duel"
          element={
            <ProtectedRoute>
              <DuelLobbyPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/duels/:duelId"
          element={
            <ProtectedRoute>
              <DuelPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/games/:gameId"
          element={
            <ProtectedRoute>
              <GamePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/games/:gameId/result"
          element={
            <ProtectedRoute>
              <ResultPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/leaderboard"
          element={
            <ProtectedRoute>
              <LeaderboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <AdminPage />
            </AdminRoute>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
