import argon2 from "argon2";

const options: argon2.Options & { raw?: false } = {
  type: argon2.argon2id,
  memoryCost: 19456,
  timeCost: 2,
  parallelism: 1,
};

export function hashPassword(password: string): Promise<string> {
  if (password.length < 12) throw new Error("Password must be at least 12 characters");
  return argon2.hash(password, options);
}

export function verifyPassword(hash: string, password: string): Promise<boolean> {
  return argon2.verify(hash, password, options);
}
