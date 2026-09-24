import type { Rule } from 'antd/es/form'

export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128

/** Form rules matching the API's 8–128 character password contract.
 * An empty value is valid when editing: it means "leave the password alone". */
export function passwordRules(required: boolean): Rule[] {
  const rules: Rule[] = required
    ? [{ required: true, message: 'گذرواژه الزامی است' }]
    : []
  rules.push({
    validator: async (_rule: unknown, value: unknown) => {
      if (value === undefined || value === null || value === '') return
      if (typeof value !== 'string') throw new Error('گذرواژه باید متن باشد')
      if (value.length < PASSWORD_MIN_LENGTH) throw new Error('حداقل ۸ نویسه')
      if (value.length > PASSWORD_MAX_LENGTH) throw new Error('حداکثر ۱۲۸ نویسه')
    },
  })
  return rules
}
