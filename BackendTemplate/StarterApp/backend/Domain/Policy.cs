namespace IMS.Modernized.WebAPI.Domain;

public class Policy
{
    public int PolicyId { get; set; }
    public string PolicyNumber { get; set; } = string.Empty;
    public int ClientId { get; set; }
    public string PolicyType { get; set; } = "Auto";
    public decimal PremiumAmount { get; set; }
    public string Status { get; set; } = "Active";
    public DateTime EffectiveDate { get; set; }
    public DateTime ExpirationDate { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
