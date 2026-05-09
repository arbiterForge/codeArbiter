import type { FastifyPluginAsync } from 'fastify'
import { eq } from 'drizzle-orm'
import { db } from '../db/index.js'
import { solutions } from '../db/schema.js'
import { SolutionSchema, SolutionDetailSchema } from '../schemas/solution.js'

const solutionsRoute: FastifyPluginAsync = async (app) => {
  app.get('/', async (_request, reply) => {
    const rows = await db.select().from(solutions).orderBy(solutions.createdAt)
    const parsed = rows.map((r) => SolutionSchema.parse(r))
    return reply.send(parsed)
  })

  app.get<{ Params: { id: string } }>('/:id', async (request, reply) => {
    const [row] = await db
      .select()
      .from(solutions)
      .where(eq(solutions.id, request.params.id))
      .limit(1)

    if (!row) return reply.code(404).send({ error: 'not_found' })

    return reply.send(SolutionDetailSchema.parse(row))
  })
}

export default solutionsRoute
