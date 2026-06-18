import type { PageInput } from "./types";

export function renderSkillPage(input: PageInput): string {
  return `---
title: ${input.name}
---
# ${input.name}
${input.description}
`;
}
