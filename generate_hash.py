from infrastructure.security import get_password_hash

# Generate hash for admin123
hash_value = get_password_hash("admin123")
print(f"Hash for 'admin123':")
print(hash_value)
print(f"\nLength: {len(hash_value)} characters")

# Force CI update
