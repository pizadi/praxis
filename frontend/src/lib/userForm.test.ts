import { describe, expect, it } from 'vitest'
import type { Rule } from 'antd/es/form'

import { passwordRules, PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from './userForm'

function ruleValidator(rules: Rule[]): (rule: unknown, value: unknown) => Promise<void> {
  return (rules[rules.length - 1] as unknown as {
    validator: (rule: unknown, value: unknown) => Promise<void>
  }).validator
}

describe('passwordRules', () => {
  it('allows an empty optional value when editing', async () => {
    const validate = ruleValidator(passwordRules(false))
    await expect(validate({}, undefined)).resolves.toBeUndefined()
    await expect(validate({}, '')).resolves.toBeUndefined()
  })

  it('rejects values outside the API length contract with Persian messages', async () => {
    const validate = ruleValidator(passwordRules(false))
    await expect(validate({}, 'a'.repeat(PASSWORD_MIN_LENGTH - 1))).rejects.toThrow(
      'حداقل ۸ نویسه',
    )
    await expect(validate({}, 'a'.repeat(PASSWORD_MAX_LENGTH + 1))).rejects.toThrow(
      'حداکثر ۱۲۸ نویسه',
    )
  })

  it('accepts the boundary values and requires a new password when creating', async () => {
    const validate = ruleValidator(passwordRules(true))
    await expect(validate({}, 'a'.repeat(PASSWORD_MIN_LENGTH))).resolves.toBeUndefined()
    await expect(validate({}, 'a'.repeat(PASSWORD_MAX_LENGTH))).resolves.toBeUndefined()
    expect((passwordRules(true)[0] as { message?: string }).message).toBe('گذرواژه الزامی است')
  })
})
