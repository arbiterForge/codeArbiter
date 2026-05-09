export interface Finding {
  rule: string
  file: string
  line?: number
  message: string
}
