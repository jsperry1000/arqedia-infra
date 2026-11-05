/**
 * What a password must be, said before it is refused (5 November 2026).
 *
 * The sign-up screen asked for twelve characters and checked for twelve
 * characters, while the pool also wants an upper case letter, a lower case
 * letter and a number. The password does not leave the browser until the last
 * step, so the first anyone heard of those rules was a failure after the
 * emailed code, on a screen with no way back to the password.
 *
 * A COPY OF auth.tf's password_policy, because this screen has no account to
 * read the pool with. tests/test_signup_password.py fails if the two differ.
 * This is a courtesy; the pool is the control, and the server answers for
 * anything that gets past it.
 *
 * PLAIN LETTERS AND DIGITS ONLY. A rule that counted "É" could pass a password
 * the pool then refuses, which is the failure this exists to prevent.
 */

export const MINIMUM_LENGTH = 12;

export const PASSWORD_RULES =
  "At least twelve characters, with an upper case letter, a lower case letter "
  + "and a number.";

/** What this password still lacks, all of it at once, or null where it has
 *  everything. */
export function passwordProblem(password: string): string | null {
  const wants: string[] = [];
  if (password.length < MINIMUM_LENGTH) wants.push("at least twelve characters");
  if (!/[A-Z]/.test(password)) wants.push("an upper case letter");
  if (!/[a-z]/.test(password)) wants.push("a lower case letter");
  if (!/[0-9]/.test(password)) wants.push("a number");
  if (wants.length === 0) return null;
  const last = wants.pop() as string;
  return "Still needs " + (wants.length ? wants.join(", ") + " and " : "")
    + last + ".";
}

/** Whether the server's refusal is about the password. Every sentence it has
 *  for that begins this way (_password_problem and PASSWORD_REFUSED in
 *  lambda/signup/app.py); tests/test_signup_password.py holds it to that. */
export function isPasswordRefusal(message: string): boolean {
  return message.startsWith("That password");
}
