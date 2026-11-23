namespace IMS.Modernized.WebAPI.Domain;

public class Claim
{
    public int ClaimId { get; set; }
    public int PolicyId { get; set; }
    public string ClaimNumber { get; set; } = string.Empty;
    public decimal Amount { get; set; }
    public string Status { get; set; } = "Submitted";
    public string Description { get; set; } = string.Empty;
    public DateTime IncidentDate { get; set; }
    public DateTime ReportedDate { get; set; } = DateTime.UtcNow;
}
