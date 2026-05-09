import type { FastifyPluginAsync } from 'fastify'
import { eq } from 'drizzle-orm'
import { randomUUID } from 'node:crypto'
import { db } from '../db/index.js'
import { solutions, deployments } from '../db/schema.js'
import { CreateDeploymentBodySchema, DeploymentSchema } from '../schemas/deployment.js'
import { emit } from '../lib/audit/index.js'

const deploymentsRoute: FastifyPluginAsync = async (app) => {
  app.post<{ Params: { solutionId: string }; Body: unknown }>(
    '/:solutionId/deployments',
    async (request, reply) => {
      const [solution] = await db
        .select()
        .from(solutions)
        .where(eq(solutions.id, request.params.solutionId))
        .limit(1)

      if (!solution) return reply.code(404).send({ error: 'solution_not_found' })

      const bodyResult = CreateDeploymentBodySchema.safeParse(request.body)
      if (!bodyResult.success) {
        return reply.code(422).send({ error: 'validation_error', issues: bodyResult.error.issues })
      }

      const body = bodyResult.data
      const id = randomUUID()
      const now = new Date()

      const [row] = await db
        .insert(deployments)
        .values({
          id,
          solutionId: solution.id,
          solutionName: solution.name,
          status: 'queued',
          actorSub: request.actorSub,
          classification: body.classification,
          replicaCount: body.replicaCount,
          createdAt: now,
          updatedAt: now,
        })
        .returning()

      if (!row) return reply.code(500).send({ error: 'insert_failed' })

      const deployment = DeploymentSchema.parse({
        ...row,
        createdAt: row.createdAt.toISOString(),
        updatedAt: row.updatedAt.toISOString(),
      })

      void emit({
        ts: now.toISOString(),
        event_id: randomUUID(),
        action: 'deploy.solution',
        actor: { id: request.actorSub, type: 'user' },
        subject: { type: 'solution', id: solution.id, name: solution.name },
        outcome: 'success',
        source: { request_id: randomUUID() },
        classification: body.classification,
        metadata: { schema_version: '1.0.0', product: 'fusion-core' },
        class_uid: 6001,
        severity_id: 2,
      })

      return reply.code(201).send(deployment)
    },
  )
}

export default deploymentsRoute
