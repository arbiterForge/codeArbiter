import Fastify from 'fastify'
import cors from '@fastify/cors'
import sensible from '@fastify/sensible'
import { verifyToken } from './middleware/auth.js'
import health from './routes/health.js'
import solutionsRoute from './routes/solutions.js'
import deploymentsRoute from './routes/deployments.js'

export async function buildApp() {
  const app = Fastify({ logger: process.env.NODE_ENV !== 'test' })

  await app.register(cors, { origin: false })
  await app.register(sensible)

  // Root-level decoration — Fastify requires decorateRequest on the root
  // instance so the property is reliably initialized for every incoming request.
  app.decorateRequest('actorSub', '')

  // Root-level auth hook covers all routes; verifyToken skips public paths
  // internally so /health requires no token.
  app.addHook('onRequest', verifyToken)

  await app.register(health)

  await app.register(solutionsRoute, { prefix: '/api/v1/solutions' })
  await app.register(deploymentsRoute, { prefix: '/api/v1/solutions' })

  return app
}
